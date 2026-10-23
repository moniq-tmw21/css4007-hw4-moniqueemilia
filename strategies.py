import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from tools import calculate, lookup


ROOT = Path(__file__).parent
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "none"
MAX_ROUNDS = 10

SYSTEM_PROMPT = """
Answer questions about the fictional Nine Rivers Region.
Use lookup to obtain facts and calculate for arithmetic.
Do not invent facts. Respect correction notices and units.
Keep intermediate precision and round only the final answer.
End your response with exactly:
ANSWER: <name or yes/no> | <number>
"""


def validate_arguments(name, raw_arguments, definitions):
    if not isinstance(raw_arguments, str) or len(raw_arguments) > 4000:
        raise ValueError(
            "Tool arguments must be a JSON string under 4001 characters."
        )

    arguments = json.loads(raw_arguments)

    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a JSON object.")

    schemas = {
        item["function"]["name"]: item["function"]["parameters"]
        for item in definitions
    }

    if name not in schemas:
        raise ValueError("Unknown tool name.")

    schema = schemas[name]
    properties = schema["properties"]

    if set(arguments) - set(properties):
        raise ValueError("Unexpected argument names.")

    if not set(schema.get("required", [])) <= set(arguments):
        raise ValueError("Required arguments are missing.")

    for key, value in arguments.items():
        rule = properties[key]

        if not isinstance(value, str):
            raise ValueError(f"{key} must be a string.")

        if "enum" in rule and value not in rule["enum"]:
            raise ValueError(f"Unsupported value for {key}.")

        if len(value) < rule.get("minLength", 0):
            raise ValueError(f"{key} is too short.")

        if len(value) > rule.get("maxLength", 200):
            raise ValueError(f"{key} is too long.")

    return arguments


def run_s3(question, decimals, log_path):
    load_dotenv(ROOT / ".env")

    with (ROOT / "tool_definitions.json").open(
        encoding="utf-8"
    ) as handle:
        definitions = json.load(handle)

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.strip(),
        },
        {
            "role": "user",
            "content": (
                f"{question}\n"
                f"Round the final number to {decimals} decimal places."
            ),
        },
    ]

    record = {
        "model": MODEL,
        "strategy": "S3",
        "reasoning_effort": REASONING_EFFORT,
        "max_rounds": MAX_ROUNDS,
        "question": question,
        "decimals": decimals,
        "tool_definitions": definitions,
        "messages": messages,
        "api_calls": [],
        "tool_calls": [],
        "input_tokens": 0,
        "output_tokens": 0,
        "rounds": 0,
        "status": "running",
        "answer": None,
    }

    started = time.perf_counter()
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def save():
        record["seconds"] = time.perf_counter() - started

        log_path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    save()
    client = None

    try:
        client = OpenAI(timeout=90.0, max_retries=0)

        for round_number in range(1, MAX_ROUNDS + 1):
            record["rounds"] = round_number
            api_started = time.perf_counter()

            response = client.chat.completions.create(
                model=MODEL,
                reasoning_effort=REASONING_EFFORT,
                messages=messages,
                tools=definitions,
                tool_choice=(
                    "required" if round_number == 1 else "auto"
                ),
            )

            api_seconds = time.perf_counter() - api_started
            usage = (
                response.usage.model_dump()
                if response.usage
                else {}
            )

            record["input_tokens"] += usage.get(
                "prompt_tokens", 0
            )
            record["output_tokens"] += usage.get(
                "completion_tokens", 0
            )

            choice = response.choices[0]
            message = choice.message

            # Preserve the assistant message and its tool calls.
            messages.append(
                message.model_dump(exclude_none=True)
            )

            record["api_calls"].append({
                "round": round_number,
                "response_id": response.id,
                "seconds": api_seconds,
                "usage": usage,
                "finish_reason": choice.finish_reason,
            })

            save()

            if not message.tool_calls:
                content = message.content or ""
                lines = content.strip().splitlines()
                final_line = lines[-1] if lines else ""

                valid_format = re.fullmatch(
                    r"ANSWER:\s*[^|\n]+\s*\|\s*"
                    r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
                    r"(?:[eE][-+]?\d+)?\s*",
                    final_line,
                )

                if valid_format and choice.finish_reason == "stop":
                    record["status"] = "answered"
                    record["answer"] = content
                else:
                    record["status"] = "unanswered"
                    record["reason"] = (
                        "Missing or incomplete final answer."
                    )

                break

            for call in message.tool_calls:
                tool_started = time.perf_counter()
                arguments = None

                function_call = getattr(call, "function", None)
                name = getattr(function_call, "name", None)
                raw_arguments = getattr(
                    function_call, "arguments", None
                )

                try:
                    if call.type != "function":
                        raise ValueError("Unsupported tool type.")

                    arguments = validate_arguments(
                        name,
                        raw_arguments,
                        definitions,
                    )

                    functions = {
                        "lookup": lookup,
                        "calculate": calculate,
                    }

                    result = functions[name](**arguments)

                except Exception as exc:
                    result = {"error": str(exc)}

                record["tool_calls"].append({
                    "round": round_number,
                    "id": call.id,
                    "name": name,
                    "raw_arguments": raw_arguments,
                    "arguments": arguments,
                    "result": result,
                    "seconds": (
                        time.perf_counter() - tool_started
                    ),
                })

                # Return one result for every requested tool call.
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(
                        result,
                        ensure_ascii=False,
                    ),
                })

                save()

        if record["status"] == "running":
            record["status"] = "unanswered"
            record["reason"] = (
                "Maximum number of rounds reached."
            )

    except Exception as exc:
        record["status"] = "api_error"

        api_key = os.getenv("OPENAI_API_KEY", "")
        error_message = str(exc)

        if api_key:
            error_message = error_message.replace(
                api_key,
                "[REDACTED]",
            )

        record["reason"] = (
            f"{type(exc).__name__}: {error_message}"
        )

    finally:
        save()

        if client is not None:
            client.close()

    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default="Q-09")
    args = parser.parse_args()

    questions = json.loads(
        (ROOT / "data" / "questions.json").read_text(
            encoding="utf-8"
        )
    )

    selected = next(
        (
            item
            for item in questions
            if item["id"] == args.question
        ),
        None,
    )

    if selected is None:
        parser.error("Unknown question ID.")

    stamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )

    log_path = (
        ROOT
        / "outputs"
        / "pilot"
        / f"{args.question}_{stamp}.json"
    )

    result = run_s3(
        selected["question"],
        selected["decimals"],
        log_path,
    )

    print("Status:", result["status"])
    print(
        result["answer"]
        or result.get("reason", "No answer.")
    )
    print("Rounds:", result["rounds"])
    print("Input tokens:", result["input_tokens"])
    print("Output tokens:", result["output_tokens"])
    print("Log:", log_path)
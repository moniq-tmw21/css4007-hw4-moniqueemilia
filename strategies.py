import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from evaluation import parse_answer, vote_answers
from tools import calculate, lookup


ROOT = Path(__file__).parent
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "none"
MAX_ROUNDS = 10
SAMPLES = 5

COMMON_PROMPT = """
Answer questions about the fictional Nine Rivers Region.
Use only the supplied documents or facts returned by tools.
Respect correction notices, years, and units.
Do not invent facts.
Keep intermediate precision and round only the final result.
End with exactly:
ANSWER: <name or yes/no> | <number>
""".strip()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def corpus_text():
    documents = [
        json.loads(line)
        for line in (ROOT / "data" / "corpus.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]

    return "\n\n".join(
        f'{item["id"]}: {item["title"]}\n{item["text"]}'
        for item in documents
    )


def validate_arguments(name, raw, definitions):
    if not isinstance(raw, str) or len(raw) > 4000:
        raise ValueError("Invalid or oversized JSON arguments.")

    arguments = json.loads(raw)

    if not isinstance(arguments, dict):
        raise ValueError("Arguments must be a JSON object.")

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


def safe_error(exc):
    message = f"{type(exc).__name__}: {exc}"
    key = os.getenv("OPENAI_API_KEY", "")

    if key:
        message = message.replace(key, "[REDACTED]")

    return message


def run_strategy(
    strategy,
    question,
    decimals,
    log_path,
    temperature=0.7,
    vague_lookup=False,
):
    if strategy not in {"S1", "S2", "S3"}:
        raise ValueError("Unknown strategy.")

    load_dotenv(ROOT / ".env")

    definitions = read_json(ROOT / "tool_definitions.json")

    if vague_lookup:
        if strategy != "S3":
            raise ValueError("Vague lookup applies only to S3.")

        for definition in definitions:
            if definition["function"]["name"] == "lookup":
                definition["function"]["description"] = (
                    "Looks things up."
                )

    log_path = Path(log_path)

    if log_path.exists():
        raise FileExistsError("Choose a new log path.")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()

    record = {
        "model": MODEL,
        "strategy": strategy,
        "question": question,
        "decimals": decimals,
        "settings": {
            "reasoning_effort": REASONING_EFFORT,
            "temperature": temperature,
            "max_rounds": MAX_ROUNDS,
            "k": SAMPLES if strategy == "S2" else 1,
            "vague_lookup": vague_lookup,
        },
        "tool_definitions": definitions if strategy == "S3" else [],
        "conversations": [],
        "api_calls": [],
        "tool_calls": [],
        "errors": [],
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "rounds": 0,
        "status": "running",
        "answer": None,
    }

    def save():
        record["seconds"] = time.perf_counter() - started
        log_path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def make_messages():
        instructions = COMMON_PROMPT

        if strategy == "S1":
            instructions += "\nAnswer directly."
        elif strategy == "S2":
            instructions += (
                "\nSolve the question step by step, "
                "then provide the required final answer."
            )
        else:
            instructions += (
                "\nUse lookup to retrieve facts "
                "and calculate to perform arithmetic."
            )

        user_text = (
            f"{question}\n"
            f"Round the final number to {decimals} decimal places."
        )

        if strategy in {"S1", "S2"}:
            user_text = (
                "DOCUMENTS:\n"
                + corpus_text()
                + "\n\nQUESTION:\n"
                + user_text
            )

        return [
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_text},
        ]

    save()
    client = None

    try:
        client = OpenAI(timeout=90.0, max_retries=0)

        def call_model(messages, sample, round_number):
            request = {
                "model": MODEL,
                "reasoning_effort": REASONING_EFFORT,
                "messages": messages,
            }

            if temperature is not None:
                request["temperature"] = temperature

            if strategy == "S3":
                request["tools"] = definitions
                request["tool_choice"] = (
                    "required" if round_number == 1 else "auto"
                )

            call_started = time.perf_counter()
            response = client.chat.completions.create(**request)

            usage = (
                response.usage.model_dump()
                if response.usage
                else {}
            )

            record["input_tokens"] += usage.get("prompt_tokens", 0)
            record["output_tokens"] += usage.get("completion_tokens", 0)

            details = usage.get("prompt_tokens_details") or {}
            record["cached_input_tokens"] += (
                details.get("cached_tokens", 0) or 0
            )

            choice = response.choices[0]
            messages.append(
                choice.message.model_dump(exclude_none=True)
            )

            record["rounds"] += 1
            record["api_calls"].append({
                "sample": sample,
                "round": round_number,
                "response_id": response.id,
                "seconds": time.perf_counter() - call_started,
                "usage": usage,
                "finish_reason": choice.finish_reason,
            })

            save()
            return choice

        if strategy in {"S1", "S2"}:
            samples = []
            sample_count = SAMPLES if strategy == "S2" else 1

            for sample in range(1, sample_count + 1):
                messages = make_messages()

                conversation = {
                    "sample": sample,
                    "messages": messages,
                    "status": "running",
                }
                record["conversations"].append(conversation)

                try:
                    choice = call_model(messages, sample, 1)
                    content = choice.message.content or ""

                    valid = (
                        choice.finish_reason == "stop"
                        and parse_answer(content) is not None
                    )

                    conversation["status"] = (
                        "answered" if valid else "unanswered"
                    )
                    samples.append(content if valid else None)

                except Exception as exc:
                    conversation["status"] = "api_error"
                    record["errors"].append({
                        "sample": sample,
                        "message": safe_error(exc),
                    })
                    samples.append(None)

                save()

            if strategy == "S2":
                vote = vote_answers(samples, decimals)
                record["vote"] = vote
                record["status"] = vote["status"]
                record["answer"] = vote["answer"]
            else:
                record["answer"] = samples[0]
                record["status"] = (
                    "answered" if samples[0] else "unanswered"
                )

            if record["answer"] is None and record["errors"]:
                record["status"] = "api_error"

        else:
            messages = make_messages()
            record["conversations"].append({
                "sample": 1,
                "messages": messages,
            })

            for round_number in range(1, MAX_ROUNDS + 1):
                choice = call_model(messages, 1, round_number)
                message = choice.message

                if not message.tool_calls:
                    content = message.content or ""

                    if (
                        choice.finish_reason == "stop"
                        and parse_answer(content) is not None
                    ):
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
                    raw = getattr(function_call, "arguments", None)

                    try:
                        if call.type != "function":
                            raise ValueError("Unsupported tool type.")

                        arguments = validate_arguments(
                            name, raw, definitions
                        )

                        functions = {
                            "lookup": lookup,
                            "calculate": calculate,
                        }
                        result = functions[name](**arguments)

                    except Exception as exc:
                        result = {"error": safe_error(exc)}

                    record["tool_calls"].append({
                        "round": round_number,
                        "id": call.id,
                        "name": name,
                        "raw_arguments": raw,
                        "arguments": arguments,
                        "result": result,
                        "seconds": time.perf_counter() - tool_started,
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(
                            result, ensure_ascii=False
                        ),
                    })
                    save()

            if record["status"] == "running":
                record["status"] = "unanswered"
                record["reason"] = "Maximum number of rounds reached."

    except Exception as exc:
        record["status"] = "api_error"
        record["reason"] = safe_error(exc)
        record["errors"].append({
            "message": record["reason"],
        })

    finally:
        save()
        if client is not None:
            client.close()

    return record


def run_s3(question, decimals, log_path, temperature=0.7):
    return run_strategy(
        "S3",
        question,
        decimals,
        log_path,
        temperature=temperature,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strategy", choices=["S1", "S2", "S3"], default="S3"
    )
    parser.add_argument("--question", default="Q-09")
    parser.add_argument("--temperature", default="0.7")
    parser.add_argument("--vague-lookup", action="store_true")
    args = parser.parse_args()

    if args.vague_lookup and args.strategy != "S3":
        parser.error("--vague-lookup requires S3.")

    try:
        temperature = (
            None
            if args.temperature == "default"
            else float(args.temperature)
        )

        if temperature is not None and not 0 <= temperature <= 2:
            raise ValueError()

    except ValueError:
        parser.error("Temperature must be 0 to 2, or default.")

    questions = read_json(ROOT / "data" / "questions.json")

    selected = next(
        (item for item in questions if item["id"] == args.question),
        None,
    )

    if selected is None:
        parser.error("Unknown question ID.")

    stamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )

    log_path = (
        ROOT / "outputs" / "pilot"
        / f"{args.strategy}_{args.question}_{stamp}.json"
    )

    result = run_strategy(
        args.strategy,
        selected["question"],
        selected["decimals"],
        log_path,
        temperature=temperature,
        vague_lookup=args.vague_lookup,
    )

    print("Status:", result["status"])
    print(result["answer"] or result.get("reason", "No answer."))

    for item in result["errors"]:
        print("API error:", item["message"])

    print("Model calls:", result["rounds"])
    print("Input tokens:", result["input_tokens"])
    print("Output tokens:", result["output_tokens"])
    print("Seconds:", round(result["seconds"], 3))
    print("Log:", log_path)
import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from strategies import MODEL, REASONING_EFFORT


ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

definitions = json.loads(
    (ROOT / "tool_definitions.json").read_text(encoding="utf-8")
)

messages = [
    {
        "role": "user",
        "content": "Reply with OK.",
    }
]

results = {
    "model": MODEL,
    "method": (
        "Compare API prompt_tokens for identical messages "
        "with and without tool definitions."
    ),
    "measurements": [],
}

with OpenAI(timeout=90.0, max_retries=0) as client:
    for include_tools in (False, True):
        request = {
            "model": MODEL,
            "reasoning_effort": REASONING_EFFORT,
            "temperature": 0.7,
            "messages": messages,
            "max_completion_tokens": 16,
        }

        if include_tools:
            request["tools"] = definitions
            request["tool_choice"] = "none"

        response = client.chat.completions.create(**request)

        if response.usage is None:
            raise RuntimeError("The API did not return token usage.")

        results["measurements"].append({
            "tools_included": include_tools,
            "response_id": response.id,
            "usage": response.usage.model_dump(),
        })

without_tools = results["measurements"][0]["usage"]["prompt_tokens"]
with_tools = results["measurements"][1]["usage"]["prompt_tokens"]

results["additional_input_tokens"] = with_tools - without_tools

output = ROOT / "outputs" / "tool_token_measurement.json"

if output.exists():
    raise FileExistsError("Measurement file already exists; preserve it.")

output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(
    json.dumps(results, indent=2),
    encoding="utf-8",
)

print("Without tools:", without_tools)
print("With tools:", with_tools)
print("Additional input tokens:", results["additional_input_tokens"])
print("Saved:", output)
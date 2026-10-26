import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from evaluation import score_answer
from strategies import (
    MAX_ROUNDS,
    MODEL,
    REASONING_EFFORT,
    ROOT,
    SAMPLES,
    run_strategy,
)


TEMPERATURE = 0.7
STRATEGIES = ["S1", "S2", "S3"]

PRICING = {
    "input_per_million": 0.20,
    "cached_input_per_million": 0.02,
    "output_per_million": 1.20,
    "source": (
        "https://developers.openai.com/api/docs/models/"
        "gpt-5.6-luna"
    ),
    "verified_date": "2026-10-26",
    "note": (
        "Estimated standard token cost before taxes or credits."
    ),
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    Path(path).write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def file_hashes():
    names = [
        "strategies.py",
        "evaluation.py",
        "tools.py",
        "tool_definitions.json",
        "run.py",
        "data/corpus.jsonl",
        "data/questions.json",
    ]

    return {
        name: hashlib.sha256(
            (ROOT / name).read_bytes()
        ).hexdigest()
        for name in names
    }


def estimated_cost(record):
    input_tokens = record["input_tokens"]
    cached = record.get("cached_input_tokens", 0)
    output_tokens = record["output_tokens"]

    uncached = max(0, input_tokens - cached)

    return (
        uncached * PRICING["input_per_million"]
        + cached * PRICING["cached_input_per_million"]
        + output_tokens * PRICING["output_per_million"]
    ) / 1_000_000


def make_row(run_number, strategy, question, record, log_path):
    score = score_answer(
        record.get("answer"),
        question,
        record["status"],
    )

    return {
        "run": run_number,
        "strategy": strategy,
        "question": question["id"],
        "status": record["status"],
        "correct": score["correct"],
        "unanswered": score["unanswered"],
        "predicted_label": score["predicted_label"],
        "predicted_value": score["predicted_value"],
        "expected_label": question["answer"],
        "expected_value": question["value"],
        "decimals": question["decimals"],
        "input_tokens": record["input_tokens"],
        "output_tokens": record["output_tokens"],
        "cached_input_tokens": record.get(
            "cached_input_tokens", 0
        ),
        "model_calls": record["rounds"],
        "tool_calls": len(record["tool_calls"]),
        "seconds": record["seconds"],
        "cost_usd": estimated_cost(record),
        "api_errors": len(record.get("errors", [])),
        "log": str(log_path.relative_to(ROOT)),
    }


def save_reports(folder, rows, questions):
    write_json(folder / "results.json", rows)

    with (folder / "results.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0])
        )
        writer.writeheader()
        writer.writerows(rows)

    run_number = rows[0]["run"]

    lines = [
        "# Experiment results",
        "",
        "Cost is estimated from API usage and standard token rates.",
        "Total seconds is the sum of question execution times.",
        "",
        "| Run | Strategy | Correct /20 | Unanswered | "
        "Input tokens | Output tokens | "
        "Median seconds per question | Total seconds | Cost ($) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for strategy in STRATEGIES:
        group = [
            row for row in rows
            if row["strategy"] == strategy
        ]

        if not group:
            continue

        label = {
            "S1": "S1 direct",
            "S2": "S2 think and vote (k = 5)",
            "S3": "S3 tools",
        }[strategy]

        lines.append(
            f"| {run_number} | {label} | "
            f"{sum(row['correct'] for row in group)} | "
            f"{sum(row['unanswered'] for row in group)} | "
            f"{sum(row['input_tokens'] for row in group)} | "
            f"{sum(row['output_tokens'] for row in group)} | "
            f"{median(row['seconds'] for row in group):.3f} | "
            f"{sum(row['seconds'] for row in group):.3f} | "
            f"{sum(row['cost_usd'] for row in group):.6f} |"
        )

    lines.extend([
        "",
        f"## Per question: run {run_number}",
        "",
        "| Question | S1 | S2 | S3 |",
        "|---|:---:|:---:|:---:|",
    ])

    for question in questions:
        marks = []

        for strategy in STRATEGIES:
            row = next(
                (
                    item for item in rows
                    if item["question"] == question["id"]
                    and item["strategy"] == strategy
                ),
                None,
            )

            if row is None:
                marks.append("")
            else:
                marks.append("✓" if row["correct"] else "✗")

        lines.append(
            f"| {question['id']} | "
            + " | ".join(marks)
            + " |"
        )

    lines.extend([
        "",
        f"Completed evaluations: {len(rows)}/60.",
        (
            "API errors recorded: "
            f"{sum(row['api_errors'] for row in rows)}."
        ),
        (
            "Estimated run cost: $"
            f"{sum(row['cost_usd'] for row in rows):.6f}."
        ),
    ])

    (folder / "tables.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run", type=int, choices=[1, 2], required=True
    )
    args = parser.parse_args()

    questions = read_json(ROOT / "data" / "questions.json")

    if len(questions) != 20:
        parser.error("Expected exactly twenty questions.")

    folder = ROOT / "outputs" / f"run_{args.run}"
    folder.mkdir(parents=True, exist_ok=True)

    manifest_path = folder / "manifest.json"
    hashes = file_hashes()

    if manifest_path.exists():
        manifest = read_json(manifest_path)

        if manifest["file_hashes"] != hashes:
            parser.error(
                "Source or data changed since this run started. "
                "Do not combine different implementations."
            )
    else:
        manifest = {
            "run": args.run,
            "created_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "model": MODEL,
            "reasoning_effort": REASONING_EFFORT,
            "temperature": TEMPERATURE,
            "k": SAMPLES,
            "max_rounds": MAX_ROUNDS,
            "order": (
                "Questions in file order; "
                "S1 then S2 then S3 for each question."
            ),
            "pricing": PRICING,
            "file_hashes": hashes,
        }
        write_json(manifest_path, manifest)

    rows = []

    for question in questions:
        for strategy in STRATEGIES:
            log_path = (
                folder
                / strategy
                / f"{question['id']}.json"
            )

            print(
                f"Run {args.run}: "
                f"{strategy} {question['id']}",
                flush=True,
            )

            if log_path.exists():
                record = read_json(log_path)

                if record["status"] == "running":
                    parser.error(
                        f"Incomplete log: {log_path}. "
                        "Preserve it and inspect before retrying."
                    )

                print("Using saved result.", flush=True)

            else:
                record = run_strategy(
                    strategy,
                    question["question"],
                    question["decimals"],
                    log_path,
                    temperature=TEMPERATURE,
                )

            row = make_row(
                args.run,
                strategy,
                question,
                record,
                log_path,
            )

            rows.append(row)
            save_reports(folder, rows, questions)

            print(
                f"  {record['status']} | "
                f"correct={row['correct']} | "
                f"{row['seconds']:.2f}s",
                flush=True,
            )

    print("\nCompleted:", len(rows), "evaluations.")
    print("Tables:", folder / "tables.md")
    print("Detailed results:", folder / "results.csv")
    print(
        "Estimated cost: $"
        f"{sum(row['cost_usd'] for row in rows):.6f}"
    )


if __name__ == "__main__":
    main()
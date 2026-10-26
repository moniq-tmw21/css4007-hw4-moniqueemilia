import re
from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


ANSWER_PATTERN = re.compile(
    r"ANSWER:\s*([^|\n]+?)\s*\|\s*"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)"
    r"(?:[eE][-+]?\d+)?)\s*"
)


def parse_answer(text):
    """Read a finite numeric answer from the final line."""
    if not isinstance(text, str) or not text.strip():
        return None

    final_line = text.strip().splitlines()[-1]
    match = ANSWER_PATTERN.fullmatch(final_line)

    if match is None:
        return None

    label = match.group(1).strip()

    try:
        number = Decimal(match.group(2))
    except InvalidOperation:
        return None

    if not number.is_finite():
        return None

    return label, number


def round_number(number, decimals):
    """Round to the required precision using decimal arithmetic."""
    step = Decimal(1).scaleb(-decimals)

    return number.quantize(
        step,
        rounding=ROUND_HALF_UP,
    )


def score_answer(text, question, status="answered"):
    """Ground-truth fields are used only inside this evaluator."""
    parsed = parse_answer(text)

    if status != "answered" or parsed is None:
        return {
            "correct": False,
            "unanswered": True,
            "predicted_label": None,
            "predicted_value": None,
        }

    label, number = parsed
    decimals = question["decimals"]

    expected = round_number(
        Decimal(str(question["value"])),
        decimals,
    )

    tolerance = Decimal(1).scaleb(-decimals)

    correct = (
        label == question["answer"]
        and abs(number - expected) <= tolerance
    )

    return {
        "correct": correct,
        "unanswered": False,
        "predicted_label": label,
        "predicted_value": str(number),
    }


def vote_answers(samples, decimals):
    """
    Count valid answers after rounding their numeric values.
    Resolve ties using the first occurrence among tied answers.
    """
    votes = []

    for text in samples:
        parsed = parse_answer(text)

        if parsed is None:
            continue

        label, number = parsed

        try:
            rounded = round_number(number, decimals)
        except InvalidOperation:
            continue

        votes.append((label, rounded))

    if not votes:
        return {
            "status": "unanswered",
            "answer": None,
            "valid_samples": 0,
            "winning_votes": 0,
        }

    counts = Counter(votes)
    highest_count = max(counts.values())

    winner = next(
        vote
        for vote in votes
        if counts[vote] == highest_count
    )

    label, number = winner

    return {
        "status": "answered",
        "answer": f"ANSWER: {label} | {number:.{decimals}f}",
        "valid_samples": len(votes),
        "winning_votes": highest_count,
    }
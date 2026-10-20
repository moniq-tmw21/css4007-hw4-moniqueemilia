import ast
import difflib
import json
import math
import operator
import re
from pathlib import Path


CORPUS_PATH = Path(__file__).parent / "data" / "corpus.jsonl"

MAX_EXPRESSION_LENGTH = 200
MAX_AST_NODES = 100
MAX_NUMBER = 10**15

DISTRICTS = [
    "Ossbridge", "Ossford", "Tarnvale", "Kelmarsh",
    "Brightwater", "Stonecairn", "Harrowfield", "Lindenmoor",
    "Redfen", "Ashgrove", "Millbrook", "Coldharbour",
]

DISTRICT_FIELDS = {
    "population_2020",
    "population_2025",
    "area_km2",
    "budget_2025_million_tenge",
    "water_use_2025",
    "schools",
    "pupils_2025_26",
    "paved_road_km",
    "founded_year",
}

REGIONAL_FIELDS = {
    "water_tariff_2025",
    "megalitre_to_cubic_metres",
}

NUMBER = r"([0-9][0-9,]*(?:\.[0-9]+)?)"


def error(message):
    return {"error": message}


def extract_number(text, patterns):
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = float(match.group(1).replace(",", ""))
            if not math.isfinite(value):
                raise ValueError("The retrieved number is not finite.")
            return int(value) if value.is_integer() else value
    raise ValueError("The requested fact could not be found or parsed.")


def load_corpus():
    with CORPUS_PATH.open(encoding="utf-8") as handle:
        documents = [
            json.loads(line)
            for line in handle
            if line.strip()
        ]

    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("Invalid corpus document.")
        for key in ("id", "title", "text"):
            if not isinstance(document.get(key), str):
                raise ValueError(f"Missing or invalid document field: {key}")

    return documents


def lookup(entity=None, field=None, **extra):
    try:
        if extra:
            return error("Unexpected parameters.")
        if not isinstance(entity, str) or not isinstance(field, str):
            return error("entity and field must be strings.")

        if not entity.strip() or len(entity) > 100:
            return error("entity must contain 1 to 100 characters.")
        if not field.strip() or len(field) > 100:
            return error("field must contain 1 to 100 characters.")

        entity = entity.strip()
        field = field.strip()

        if entity not in DISTRICTS + ["Region"]:
            partial_matches = [
                name for name in DISTRICTS
                if name.lower().startswith(entity.lower())
            ]
            if len(partial_matches) > 1:
                return error(
                    "Ambiguous entity. Use an exact name: "
                    + ", ".join(partial_matches)
                )

            suggestions = difflib.get_close_matches(
                entity, DISTRICTS + ["Region"], n=3, cutoff=0.4
            )
            message = f"Unknown entity: {entity}."
            if suggestions:
                message += " Possible matches: " + ", ".join(suggestions)
            return error(message)

        allowed = REGIONAL_FIELDS if entity == "Region" else DISTRICT_FIELDS
        if field not in allowed:
            return error(
                "Unsupported field for this entity. Valid fields: "
                + ", ".join(sorted(allowed))
            )

        documents = load_corpus()

        if entity == "Region":
            matches = [
                document for document in documents
                if document["title"] == "Household water tariff"
            ]
        else:
            expected_title = f"{entity} district profile (2025)"
            matches = [
                document for document in documents
                if document["title"] == expected_title
                and "ARCHIVED" not in document["text"].upper()
            ]

        if len(matches) != 1:
            return error(
                "Expected exactly one authoritative document; "
                f"found {len(matches)}."
            )

        document = matches[0]
        text = document["text"]
        sources = [document["id"]]

        if field == "population_2025":
            value = extract_number(text, [
                rf"2025 census (?:recorded|counted)\s+{NUMBER}\s+residents",
                rf"\band\s+{NUMBER}\s+in 2025\b",
            ])
            unit, year = "residents", 2025

        elif field == "population_2020":
            value = extract_number(text, [
                rf"2020 census had recorded\s+{NUMBER}",
                rf"{NUMBER}\s+at the 2020 census",
                rf"Census population:\s*{NUMBER}\s+in 2020",
            ])
            unit, year = "residents", 2020

        elif field == "area_km2":
            value = extract_number(
                text, [rf"{NUMBER}\s+square kilometres"]
            )
            unit, year = "km2", 2025

            corrections = [
                item for item in documents
                if item["title"] == f"Correction notice - {entity}"
            ]
            if len(corrections) > 1:
                return error("Multiple correction notices require review.")
            for notice in corrections:
                value = extract_number(
                    notice["text"],
                    [rf"correct area is\s+{NUMBER}\s+square kilometres"],
                )
                sources.append(notice["id"])

        elif field == "budget_2025_million_tenge":
            value = extract_number(
                text, [rf"{NUMBER}\s+million tenge"]
            )
            unit, year = "million tenge", 2025

        elif field == "water_use_2025":
            match = re.search(
                rf"{NUMBER}\s+(megalitres|cubic metres)",
                text,
                flags=re.IGNORECASE,
            )
            if not match:
                return error("Water use or its unit could not be parsed.")
            value = float(match.group(1).replace(",", ""))
            unit, year = match.group(2).lower(), 2025

        elif field == "schools":
            value = extract_number(text, [rf"{NUMBER}\s+schools"])
            unit, year = "schools", 2025

        elif field == "pupils_2025_26":
            value = extract_number(text, [rf"{NUMBER}\s+pupils"])
            unit, year = "pupils", "2025/26"

        elif field == "paved_road_km":
            value = extract_number(text, [rf"{NUMBER}\s+km\b"])
            unit, year = "km", 2025

        elif field == "founded_year":
            value = extract_number(text, [rf"founded in\s+{NUMBER}"])
            unit, year = "year", None

        elif field == "water_tariff_2025":
            value = extract_number(
                text, [rf"2025.*?{NUMBER}\s+tenge per cubic metre"]
            )
            unit, year = "tenge per cubic metre", 2025

        else:
            match = re.search(
                r"One megalitre is\s+([0-9,]+)\s+cubic metres",
                text,
                flags=re.IGNORECASE,
            )
            if not match:
                return error("The conversion factor could not be parsed.")
            value = int(match.group(1).replace(",", ""))
            unit, year = "cubic metres per megalitre", None

        return {
            "value": value,
            "unit": unit,
            "year": year,
            "sources": sources,
        }

    except Exception as exc:
        return error(f"Lookup failed: {exc}")


BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def check_number(value):
    if type(value) not in (int, float):
        raise ValueError("Only real numeric literals are allowed.")
    if abs(value) > MAX_NUMBER or not math.isfinite(value):
        raise ValueError("Numeric magnitude exceeds the permitted range.")
    return value


def evaluate_node(node):
    if isinstance(node, ast.Constant):
        return check_number(node.value)

    if isinstance(node, ast.UnaryOp):
        operation = UNARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise ValueError("Unsupported unary operator.")
        return check_number(operation(evaluate_node(node.operand)))

    if isinstance(node, ast.BinOp):
        operation = BINARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise ValueError("Unsupported operator. Powers are not allowed.")

        left = evaluate_node(node.left)
        right = evaluate_node(node.right)

        if isinstance(node.op, ast.Div) and right == 0:
            raise ValueError("Division by zero is not allowed.")

        return check_number(operation(left, right))

    raise ValueError(
        "Unsupported syntax. Names, calls, and attributes are not allowed."
    )


def calculate(expression=None, **extra):
    try:
        if extra:
            return error("Unexpected parameters.")
        if not isinstance(expression, str):
            return error("expression must be a string.")
        if not expression.strip():
            return error("The expression is empty.")
        if len(expression) > MAX_EXPRESSION_LENGTH:
            return error("The expression exceeds 200 characters.")

        tree = ast.parse(expression.strip(), mode="eval")

        if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
            return error("The expression exceeds 100 AST nodes.")

        result = evaluate_node(tree.body)
        return {"result": float(result)}

    except SyntaxError:
        return error("The expression has invalid syntax.")
    except Exception as exc:
        return error(str(exc))
import pytest

from tools import calculate, lookup


def test_lookup_2025_population():
    result = lookup("Ossbridge", "population_2025")
    assert result == {
        "value": 52904,
        "unit": "residents",
        "year": 2025,
        "sources": ["NR-01"],
    }


def test_lookup_misspelled_name():
    result = lookup("Ossbrige", "population_2025")
    assert "error" in result
    assert "Ossbridge" in result["error"]


def test_lookup_similar_names_are_distinct():
    bridge = lookup("Ossbridge", "population_2025")
    ford = lookup("Ossford", "population_2025")

    assert bridge["value"] == 52904
    assert ford["value"] == 30982
    assert bridge["sources"] != ford["sources"]


def test_lookup_ambiguous_name():
    result = lookup("Oss", "population_2025")
    assert "error" in result
    assert "Ambiguous" in result["error"]


@pytest.mark.parametrize(
    "district, expected, current_source, archived_source",
    [
        ("Tarnvale", 71388, "NR-03", "NR-13"),
        ("Kelmarsh", 24117, "NR-04", "NR-14"),
    ],
)
def test_lookup_excludes_archived_profiles(
    district, expected, current_source, archived_source
):
    result = lookup(district, "population_2025")
    assert result["value"] == expected
    assert current_source in result["sources"]
    assert archived_source not in result["sources"]


def test_lookup_applies_correction():
    result = lookup("Brightwater", "area_km2")
    assert result["value"] == 921.4
    assert result["sources"] == ["NR-05", "NR-16"]


def test_lookup_preserves_water_unit():
    result = lookup("Lindenmoor", "water_use_2025")
    assert result["value"] == 2151400
    assert result["unit"] == "cubic metres"


def test_lookup_water_tariff():
    result = lookup("Region", "water_tariff_2025")
    assert result["value"] == pytest.approx(142.35)
    assert result["sources"] == ["NR-15"]


def test_lookup_unit_conversion():
    result = lookup("Region", "megalitre_to_cubic_metres")
    assert result["value"] == 1000
    assert result["year"] is None


def test_lookup_unsupported_field():
    assert "error" in lookup("Ossbridge", "unknown_field")


def test_lookup_invalid_arguments():
    assert "error" in lookup(123, "population_2025")
    assert "error" in lookup("Ossbridge")
    assert "error" in lookup(
        "Ossbridge", "population_2025", unexpected=True
    )


def test_calculate_required_multiplication():
    result = calculate("48317 * 1.0947")
    assert result["result"] == pytest.approx(52892.6199)


def test_calculate_parentheses_and_unary_minus():
    result = calculate("-(3 + 4) * 2")
    assert result["result"] == -14.0


def test_calculate_q09():
    result = calculate("37203 / 758.6 - 44675 / 921.4")
    assert result["result"] == pytest.approx(
        0.5556561156, abs=1e-9
    )


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo hi')",
        "(1).__class__",
        "9**9**9",
    ],
)
def test_calculate_rejects_dangerous_inputs(expression):
    assert "error" in calculate(expression)


def test_calculate_division_by_zero():
    result = calculate("1 / 0")
    assert "error" in result
    assert "Division by zero" in result["error"]


def test_calculate_large_result():
    assert "error" in calculate("1000000000000000 * 2")


def test_calculate_expression_length_limit():
    assert "error" in calculate("1" * 201)


def test_calculate_ast_node_limit():
    assert "error" in calculate("+".join(["1"] * 40))


@pytest.mark.parametrize("expression", ["", "1 +", "True", "abs(-1)"])
def test_calculate_invalid_expressions(expression):
    assert "error" in calculate(expression)


def test_calculate_invalid_arguments():
    assert "error" in calculate(123)
    assert "error" in calculate()
    assert "error" in calculate("1 + 2", unexpected=True)
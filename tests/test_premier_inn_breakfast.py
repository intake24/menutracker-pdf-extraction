from pathlib import Path

import pytest

from pipeline.allergens import UnknownAllergen
from pipeline.parsers.premier_inn_breakfast import parse, parse_pages

PDF = Path(__file__).resolve().parent.parent / "inputs" / "beefeater_ss25_breakfast_menu_allergy_nutrition_v1.pdf"
SOURCE = {"markers": {"": "No"}}

MAY_COL = 70
ENERGY = "                 Energy      Fat      Saturates      Carbohydrates      Sugars      Protein      Salt"
NUTRITION = "                 698 kJ / 167 kcal      7.7 g      4.4 g      19.9 g      2.3 g      3.8 g      0.41 g"
HEADING = "UNLIMITED COOKED BREAKFAST (per item)"


def contains_line(contains: str, may: str) -> str:
    return f"{'      Contains: ' + contains:<{MAY_COL}}May Contain: {may}"


@pytest.fixture(scope="module")
def rows():
    return parse(PDF, SOURCE)


def test_every_item_parsed_without_flags(rows):
    assert len(rows) == 59  # = number of "Contains:" lines in the PDF
    assert not [r for r in rows if r.get("flags")]


def test_croissant(rows):
    croissant = next(r for r in rows if r["Product_Name"] == "Croissant")
    assert croissant["Category"] == "PREMIER INN BREAKFAST - UNLIMITED CONTINENTAL - BAKERY (per item/slice)"
    assert croissant["Diet"] == "V" and croissant["source_page"] == 2
    assert croissant["energykJ_Per Portion"] == "698" and croissant["salt_Per Portion"] == "0.41"
    assert croissant["soya"] == "May contain" and croissant["treeNutSource"] == "may: Almond, Hazelnut"
    assert croissant["celery"] == "No"


def test_amounts_move_to_serving_size_descriptions_stay(rows):
    by_name = {r["Product_Name"]: r for r in rows}
    assert (by_name["Kelloggs Muesli Fruit"]["Serving_Size"], by_name["Kelloggs Muesli Fruit"]["Serving_Size_Unit"]) == ("45", "g")
    assert "Weetabix (per 2 biscuits)" in by_name and by_name["Weetabix (per 2 biscuits)"]["Serving_Size"] == ""
    assert by_name["Black Pudding (per slice)"]["Diet"] == ""


def test_every_section_carries_the_menu_title(rows):
    assert all(r["Category"].startswith("PREMIER INN BREAKFAST - ") for r in rows)
    assert {r["Category"] for r in rows} >= {"PREMIER INN BREAKFAST - UNLIMITED COOKED BREAKFAST (per item)"}


def test_block_split_across_page_break():
    page1 = "\n".join([
        HEADING,
        "      Marmite Portions - VE          V",
        contains_line("Cereals containing Gluten (Barley, Oats, Rye,", "No major allergens"),
        " Published on : March 27, 2025",
    ])
    page2 = "\n".join(["      Wheat), Celery", ENERGY, "   Per Portion:", NUTRITION])
    [row] = parse_pages([page1, page2], "No")
    assert row["Product_Name"] == "Marmite Portions" and row["Diet"] == "VE"
    assert row["Category"] == "PREMIER INN BREAKFAST - UNLIMITED COOKED BREAKFAST (per item)"
    assert row["wheat"] == "Yes" and row["celery"] == "Yes" and row["egg"] == "No"
    assert row["source_page"] == 2


def test_item_without_nutrition_is_flagged():
    page = "\n".join([
        HEADING,
        "      Lonely Toast - V",
        contains_line("Egg", "No major allergens"),
        "      Hash Brown (per piece) - VE    V",
        contains_line("No major allergens", "No major allergens"),
        ENERGY, "   Per Portion:", NUTRITION,
    ])
    first, second = parse_pages([page], "No")
    assert first["Product_Name"] == "Lonely Toast" and first["egg"] == "Yes"
    assert first["flags"] == "error: no nutrition line found"
    assert second["Product_Name"] == "Hash Brown (per piece)" and "flags" not in second


def test_unknown_allergen_names_item():
    page = "\n".join([HEADING, "      Mystery Pie", contains_line("Lupine", "No major allergens"), ENERGY, NUTRITION])
    with pytest.raises(UnknownAllergen, match="Mystery Pie"):
        parse_pages([page], "No")


def test_heading_ends_an_item_without_nutrition():
    page = "\n".join([
        HEADING,
        "      Lonely Toast - V",
        contains_line("Egg", "No major allergens"),
        "UNLIMITED CONTINENTAL - DRINKS (per serving)",
        "      Apple Juice - VE",
        contains_line("No major allergens", "No major allergens"),
        ENERGY, "   Per Portion:", NUTRITION,
    ])
    first, second = parse_pages([page], "No")
    assert first["Product_Name"] == "Lonely Toast" and first["egg"] == "Yes"
    assert first["flags"] == "error: no nutrition line found"
    assert second["Category"] == "PREMIER INN BREAKFAST - UNLIMITED CONTINENTAL - DRINKS (per serving)"


def test_trace_values_in_the_nutrition_line_are_kept_as_printed():
    trace = "                 16 kJ / 4 kcal      Trace g      0.0 g      0.9 g      0.0 g      0.0 g      <0.1 g"
    page = "\n".join([HEADING, "      Sugar Sachet - VE", contains_line("No major allergens", "No major allergens"),
                      ENERGY, trace])
    [row] = parse_pages([page], "No")
    assert row["fat_Per Portion"] == "Trace" and row["salt_Per Portion"] == "<0.1" and "flags" not in row


def test_unreadable_nutrition_line_raises():
    bad = "                 16 kJ / 4 kcal      ? g      0.0 g      0.9 g      0.0 g      0.0 g      0.1 g"
    page = "\n".join([HEADING, "      Sugar Sachet - VE", contains_line("No major allergens", "No major allergens"),
                      ENERGY, bad])
    with pytest.raises(ValueError, match="Sugar Sachet"):
        parse_pages([page], "No")


def test_wrapped_item_name_is_rejoined():
    page = "\n".join([
        HEADING,
        "      Garden Gourmet Vegan Sausage with Extra",
        "      Long Name (per piece) - VE           V",
        contains_line("Soya", "No major allergens"),
        ENERGY, "   Per Portion:", NUTRITION,
    ])
    [row] = parse_pages([page], "No")
    assert row["Product_Name"] == "Garden Gourmet Vegan Sausage with Extra Long Name (per piece)"


def test_spelt_and_kamut_are_not_stated(rows):
    # The guide folds spelt and khorasan into "Wheat", so it never declares them absent.
    assert {r["spelt"] for r in rows} == {""} and {r["kamut"] for r in rows} == {""}

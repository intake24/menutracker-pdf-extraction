from pathlib import Path

import pytest
import yaml

from pipeline.parsers import product_blocks as pb

ROOT = Path(__file__).resolve().parent.parent
SOURCE = yaml.safe_load((ROOT / "config" / "chains.yaml").read_text())["47_Coffee1"]["sources"][0]
PDF = ROOT / "inputs" / SOURCE["pdf"]


@pytest.fixture(scope="module")
def rows():
    return {(r["Product_Name"], r["source_page"]): r for r in pb.parse(PDF, SOURCE)}


def one(rows, name):
    return next(r for (n, _), r in rows.items() if n == name)


def w(text, i, bold=False, size=5.3):
    return {"text": text, "x0": i * 20, "x1": i * 20 + 15, "top": 10, "bottom": 16, "size": size, "fontname": "Gothic-Bold" if bold else "Gothic"}


def test_every_product_of_the_guide_is_a_row_including_the_last_one_of_a_page(rows):
    assert len(rows) == 92 and ("Cherry & Coconut Mini Loaf", 9) in rows       # no rule is printed under the last row of a page


def test_a_long_name_keeps_all_its_words_and_the_diet_tag_is_kept_as_printed(rows):
    assert one(rows, "Blackberry & Apple Crumble Jack**")["Diet"] == "(Vg)"
    assert one(rows, "Cherry & Coconut Mini Loaf")["Diet"] == "(V/GF)" and one(rows, "Summer Cupcakes")["Diet"] == "(V)"
    assert "Diet" not in one(rows, "BLT")


def test_sections_come_from_the_page_heading_and_from_titles_between_rows(rows):
    assert one(rows, "Almond Croissant")["Category"] == "PASTIRES"      # printed so
    assert one(rows, "Lemon Drizzle Cake")["Category"] == "CAKES" and one(rows, "Sausage Bap")["Category"] == "BAPS"
    assert one(rows, "Porridge Plain")["notes"].startswith("Porridge is made with Whole Milk as standard")


def test_nutrition_in_both_columns_and_the_portion_weight(rows):
    r = one(rows, "Almond Croissant")
    assert (r["energykCal_Per 100g/ml"], r["energykCal_Per Portion"], r["Serving_Size"], r["Serving_Size_Unit"]) == ("399", "338", "83", "g")
    assert one(rows, "Oat & Raisin Cookie")["energykJ_Per 100g/ml"] == "1,702"   # printed with a thousands comma, kept


def test_allergens_are_the_bold_capitals_and_the_may_contain_sentence(rows):
    r = one(rows, "Almond Croissant")
    assert (r["wheat"], r["gluten"], r["egg"], r["milk"], r["sesame"], r["soya"]) == ("Yes", "Yes", "Yes", "Yes", "May contain", "May contain")
    assert (r["treeNuts"], r["treeNutSource"]) == ("Yes", "Almond") and r["peanut"] == "No"
    assert one(rows, "Kettle Sea Salt Crisps")["milk"] == "No"                 # the guide names every allergen in capitals: unnamed is No


def test_a_factory_sentence_is_a_may_contain_and_a_bold_word_in_lower_case_counts(rows):
    assert one(rows, "Oat & Raisin Cookie")["treeNuts"] == "May contain" and one(rows, "Oat & Raisin Cookie")["egg"] == "Yes"
    g = one(rows, "Gianduiotto Mini Chocolate")
    assert (g["soya"], g["treeNuts"], g["treeNutSource"], g["milk"]) == ("Yes", "Yes", "Hazelnut", "May contain")


def test_a_row_with_several_declarations_takes_the_allergens_of_all_of_them(rows):
    r = one(rows, "Summer Cupcakes")
    assert (r["egg"], r["milk"], r["sulphite"], r["soya"]) == ("Yes", "Yes", "Yes", "May contain")


def test_a_bold_capital_word_that_is_not_an_allergen_word_stops_the_run():
    with pytest.raises(ValueError, match="FRUMP"):
        pb._allergens([w("FRUMP", 1, bold=True)], SOURCE, 3, "Thing")
    got = pb._allergens([w("Salt", 0), w("MILK", 1, bold=True), w("May", 2), w("contain", 3), w("NUTS", 4)], SOURCE, 3, "Thing")
    assert (got["milk"], got["treeNuts"], got["wheat"]) == ("Yes", "May contain", "No")

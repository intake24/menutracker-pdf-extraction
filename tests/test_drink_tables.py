from pathlib import Path

import pytest
import yaml

from pipeline.parsers import drink_tables as dt

ROOT = Path(__file__).resolve().parent.parent
SOURCE = next(s for s in yaml.safe_load((ROOT / "config" / "chains.yaml").read_text())["47_Coffee1"]["sources"] if s["parser"] == "drink_tables")
PDF = ROOT / "inputs" / SOURCE["pdf"]


@pytest.fixture(scope="module")
def rows():
    return dt.parse(PDF, SOURCE)


def pick(rows, name, size=None, page=None, serving=None):
    got = [r for r in rows if r["Product_Name"] == name and (size is None or r.get("Size") == size) and (page is None or r["source_page"] == page)
           and (serving is None or r.get("Serving_Size") == serving)]
    assert len(got) == 1, (name, size, len(got))
    return got[0]


def test_every_product_size_and_syrup_portion_is_a_row(rows):
    assert len(rows) == 371     # the count Pearl Scan has, every figure of which agrees


def test_size_rows_share_the_name_and_allergens_printed_once(rows):
    single, double = pick(rows, "Macchiato - Whole Milk", "Single"), pick(rows, "Macchiato - Whole Milk", "Double")
    assert single["milk"] == double["milk"] == "Yes" and single["energykCal_Per 100g/ml"] == "34" and (single["energykCal_Per Portion"], double["energykCal_Per Portion"]) == ("9", "9")
    assert single["Category"] == "MACCHIATO" and single["Product_Description"] == "Coffee#1 blend Espresso and foamed milk"


def test_oat_is_listed_without_gluten_and_a_drink_with_no_allergen_text_has_none(rows):
    oat = pick(rows, "Macchiato - Gluten Free Oat", "Single")
    assert (oat["oats"], oat["gluten"], oat["milk"]) == ("Yes", "No", "No")
    assert pick(rows, "Espresso", "Single")["milk"] == "No"
    assert pick(rows, "Macchiato - Coconut", "Single")["soya"] == "Yes"        # printed so


def test_wrapped_names_and_names_without_a_rule_keep_all_their_words(rows):
    assert pick(rows, "Caramel Milkshake - Whole Milk", page=20)["milk"] == "Yes"
    smoothie = pick(rows, "Strawberry, Cherry, Mango, Banana, Raspberry & Blackcurrant", "Regular")
    assert smoothie["energykCal_Per Portion"] == "179"
    assert pick(rows, "Passionfruit & Lemon Iced Tea", "Regular")["energykCal_Per Portion"] == "56"
    assert pick(rows, "Mini Marshmallows")["energykCal_Per 100g/ml"] == "329"      # "Mini" is part of a bold name, not a size


def test_sizes_in_ounces_are_also_the_serving_size_and_syrup_portions_are_rows_of_their_own(rows):
    assert (pick(rows, "Caramel Macchiato - Whole Milk", "12oz")["Serving_Size"], pick(rows, "Caramel Macchiato - Whole Milk", "12oz")["Serving_Size_Unit"]) == ("12", "oz")
    small, large = pick(rows, "Caramel Sauce", serving="15"), pick(rows, "Caramel Sauce", serving="22.5")
    assert (small["Serving_Size_Unit"], small["energykCal_Per Portion"], large["energykCal_Per Portion"], small["milk"]) == ("ml", "45", "68", "Yes")


def test_vitamin_content_belongs_to_its_row(rows):
    assert pick(rows, "Pink Limeade with added Vitamin C", "Regular")["vitaminC_Per Portion"] == "20.64"
    assert pick(rows, "Mango & Passionfruit with added vintamin B12", "Large")["vitaminB12_Per Portion"] == "2.944"


def w(text, x, top, bold=False, size=9.5):
    return {"text": text, "x0": x, "x1": x + 20, "top": top, "bottom": top + 8, "size": size, "fontname": "Calibri-Bold" if bold else "Calibri"}


def test_figures_with_no_table_header_an_unknown_group_label_and_a_bad_column_count_raise():
    figures = [w(str(i), 200 + 25 * i, 100) for i in range(18)]
    with pytest.raises(ValueError, match="no table header"):
        dt.parse_page(figures, [], SOURCE, 3)
    page = [w("TITLE", 100, 20, bold=True, size=11), w("Per", 300, 50, bold=True), w("100pints", 330, 50, bold=True)] + figures
    with pytest.raises(ValueError, match="100pints"):
        dt.parse_page(page, [60, 130], SOURCE, 3)

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


def test_two_names_between_two_rules_stop_the_run():
    rows_ = []
    for top in (100, 112, 124, 140):
        rows_ += [w("Regular", 240, top)] + [w(str(i), 300 + 25 * i, top) for i in range(18)]
    page = [w("TITLE", 100, 20, bold=True, size=11), w("Per", 300, 50, bold=True), w("100ml", 330, 50, bold=True),
            w("Per", 700, 50, bold=True), w("product", 730, 50, bold=True), w("Latte", 60, 106, bold=True), w("MILK", 190, 106),
            w("Mocha", 60, 124, bold=True), w("MILK", 190, 124), w("Tea", 60, 140, bold=True)] + rows_
    # a rule under Latte but none between Mocha and Tea: two products would be read as one
    with pytest.raises(ValueError, match="more than one name"):
        dt.parse_page(page, [60, 90, 118, 150], SOURCE, 3)


def test_a_vitamin_value_that_does_not_match_its_name_or_sits_by_no_row_raises():
    def line(text, x, top, bold=False, size=9.5):
        return w(text, x, top, bold=bold, size=size)
    figures = lambda top: [line("Regular", 240, top)] + [w(str(i), 300 + 25 * i, top) for i in range(18)]
    page = [line("TITLE", 100, 20, bold=True, size=11), line("Per", 300, 50, bold=True), line("100ml", 330, 50, bold=True), line("Per", 700, 50, bold=True),
            line("product", 730, 50, bold=True), line("Tea", 60, 106, bold=True), line("2.21ug", 150, 106)] + figures(106)
    with pytest.raises(ValueError, match="does not match the name"):
        dt.parse_page(page, [60, 90, 160], SOURCE, 3)
    page = page[:-19] + [line("2.21ug", 150, 140)] + figures(106)
    with pytest.raises(ValueError, match="by no row"):
        dt.parse_page(page, [60, 90, 160], SOURCE, 3)

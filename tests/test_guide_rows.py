from pathlib import Path

import pytest
import yaml

from pipeline.parsers import guide_rows as gr
from pipeline.parsers import modifier_matrix as mm

ROOT = Path(__file__).resolve().parent.parent
SOURCES = yaml.safe_load((ROOT / "config" / "chains.yaml").read_text())["7_Starbucks"]["sources"]
FOOD, BEV, MOD = SOURCES
FOOD_PDF, BEV_PDF = ROOT / "inputs" / FOOD["pdf"], ROOT / "inputs" / BEV["pdf"]


@pytest.fixture(scope="module")
def food():
    return gr.parse(FOOD_PDF, FOOD)


@pytest.fixture(scope="module")
def bev():
    return gr.parse(BEV_PDF, BEV)


def pick(rows, name, size=None, page=None):
    got = [r for r in rows if r["Product_Name"] == name and (size is None or r.get("Size") == size) and (page is None or r["source_page"] == page)]
    assert len(got) == 1, (name, size, len(got))
    return got[0]


def test_every_food_product_is_a_row_including_the_last_of_a_page(food):
    assert len(food) == 93
    assert pick(food, "Pain Au Chocolat (at selected stores)")["source_page"] == 7        # no rule is printed under the last row of a page


def test_a_food_row_has_diet_cells_figures_and_the_summarised_allergens(food):
    r = pick(food, "Boston Cream Muffin")
    assert (r["Suitable_for_Vegetarian"], r["Suitable_for_Vegan"], r["energykCal_Per Portion"], r["salt_Per Portion"]) == ("Y", "N", "449", "0.5")
    assert (r["wheat"], r["gluten"], r["egg"], r["soya"], r["milk"], r["peanut"]) == ("Yes", "Yes", "Yes", "Yes", "Yes", "No")
    assert r["Category"] == "Seasonal Menu - Loaf Cakes & Muffins"
    assert pick(food, "Raspberry & Coconut Loaf Cake")["treeNutSource"] == "Almond"


def test_gluten_free_oats_set_oats_but_not_gluten_and_a_dash_in_the_allergen_column_is_none(food):
    bar = pick(food, "Gluten Free Fruit & Nut Bar")
    assert (bar["oats"], bar["gluten"]) == ("Yes", "No")
    assert all(pick(food, "Banana (per unit =whole)")[a] == "No" for a in ("milk", "wheat", "soya"))


def test_a_figure_printed_with_its_unit_is_kept_and_a_blank_cell_stays_blank(food):
    r = pick(food, "Cloudy Apple Juice")
    assert r["fat_Per Portion"] == "<0.5g" and "fibre_Per Portion" in r
    assert r["Category"].startswith("Chocolate, Snacks & Bottled Drinks")


def test_the_allergen_column_and_the_bold_capitals_of_the_ingredients_agree_on_every_product(food, bev):
    assert not [r["Product_Name"] for r in food + bev if "allergen column and the bold capitals" in r.get("flags", "")]


def test_a_drink_has_a_row_per_size_with_the_shared_name_and_allergens(bev):
    assert len(bev) == 1426
    tall = pick(bev, "Tiramisu Cream Iced Oat Shaken Espresso - skimmed milk", "Tall")
    venti = pick(bev, "Tiramisu Cream Iced Oat Shaken Espresso - skimmed milk", "Venti")
    assert (tall["energykCal_Per Portion"], venti["energykCal_Per Portion"], tall["caffeine_Per Portion"], venti["caffeine_Per Portion"]) == ("272", "330", "85.5", "171")
    assert tall["milk"] == venti["milk"] == "Yes" and tall["soya"] == "No"
    almond = pick(bev, "Tiramisu Cream Iced Oat Shaken Espresso - almond drink", "Tall")
    assert (almond["milk"], almond["treeNuts"], almond["treeNutSource"]) == ("Yes", "Yes", "Almond")


def test_sizes_are_read_by_column_and_the_menu_is_the_running_head_without_its_version(bev):
    assert {r.get("Size") for r in bev} >= {"Tall", "Grande", "Venti", "Single", "Doppio", "Short", "Mini"}
    assert all(r["Category"] and "Version" not in r["Category"] for r in bev)


def w(text, x, top, bold=False, size=6.0):
    return {"text": text, "x0": x, "x1": x + 10, "top": top, "bottom": top + 6, "size": size, "fontname": "Condensed-Bold" if bold else "Condensed-Regular"}


def test_a_summary_column_that_differs_from_the_bold_capitals_is_flagged_and_a_row_with_no_name_raises():
    src = {**FOOD, "diet_columns": []}
    rules = [(0, 0, 800), (110, 20, 780), (200, 136, 523), (300, 20, 780), (525, 0, 800)]
    figures = [w(str(i), 530 + 23 * i, 150) for i in range(9)]
    base = [w("Product", 24, 100, bold=True), w("| Food | Menu", 24, 10)]
    row = [w("Cake", 24, 150, bold=True)] + [w("Sugar", 140, 150), w("flour.", 160, 150)] + figures + [w("MILK", 735, 150, bold=True)]
    got = gr.parse_page(base + row, rules, src, 4)
    assert "differ on milk" in got[0]["flags"] and got[0]["milk"] == "Yes"
    with pytest.raises(ValueError, match="no name"):
        gr.parse_page(base + row[1:], rules, src, 4)


def test_the_modifiers_have_calories_a_name_beside_their_lines_and_ticks_found_by_position():
    rows = mm.parse(ROOT / "inputs" / MOD["pdf"], MOD)
    assert len(rows) == 38
    drizzle = next(r for r in rows if r["Product_Name"] == "Caramel Drizzle")
    assert (drizzle["energykCal_Per Portion"], drizzle["milk"], drizzle["soya"], drizzle["wheat"], drizzle["Size"]) == ("25", "Yes", "Yes", "No", "per serving")
    cream = [r for r in rows if r["Product_Name"] == "Whipped Cream"]
    assert [r["Size"] for r in cream] == ["Tall", "Grande", "Venti"] and all(r["milk"] == "Yes" for r in cream)
    syrup = next(r for r in rows if r["Product_Name"] == "Almond Flavour Syrup" and r["Size"].startswith("Frappuccino"))
    assert syrup["energykCal_Per Portion"] == "9" and syrup["milk"] == "No"


def test_an_unknown_modifier_label_raises():
    chars = [{"text": c, "x0": 100, "x1": 106, "top": 100 + 7 * i, "bottom": 106 + 7 * i, "upright": False} for i, c in enumerate("xirtaM"[::-1])]
    with pytest.raises(ValueError, match="not in `labels`"):
        mm._columns(chars, MOD["labels"], 63)


def _page(src, rows_, rules=None):
    rules = rules or [(0, 0, 800), (110, 20, 780), (200, 136, 523), (300, 20, 780), (525, 0, 800)]
    return gr.parse_page([w("Product", 24, 100, bold=True), w("| Food | Menu", 24, 10)] + rows_, rules, {**src, "diet_columns": []}, 4)


def _figs(top, n=9, skip=()):
    return [w(str(i + 1), 530 + 23 * i, top) for i in range(n) if i not in skip]


def test_a_blank_figure_cell_stays_blank_and_the_following_figures_keep_their_columns():
    full = [w("Cake", 24, 150, bold=True), w("Sugar", 140, 150)] + _figs(150) + [w("MILK", 735, 150, bold=True)]
    got = _page(FOOD, full + [w("Pie", 24, 250, bold=True), w("Sugar", 140, 250)] + _figs(250, skip=(6,)) + [w("MILK", 735, 250, bold=True)],
                [(0, 0, 800), (110, 20, 780), (200, 136, 523), (300, 136, 523), (525, 0, 800)])
    pie = next(r for r in got if r["Product_Name"] == "Pie")
    assert "fibre_Per Portion" not in pie and (pie["protein_Per Portion"], pie["salt_Per Portion"]) == ("8", "9")


def test_two_drinks_read_as_one_because_a_rule_is_missing_stop_the_run():
    src = {**BEV}
    rows_ = []
    for k, top in enumerate((150, 160, 170, 200, 210, 220)):
        rows_ += [w(["Tall", "Grande", "Venti"][k % 3], 480, top)] + [w(str(i + 1), 520 + 23 * i, top) for i in range(10)]
    rows_ += [w("Latte", 24, 160, bold=True), w("Mocha", 24, 210, bold=True), w("Sugar", 100, 150), w("MILK", 735, 160, bold=True)]
    with pytest.raises(ValueError, match="two names in one row|a size appears twice"):
        gr.parse_page([w("Product", 24, 100, bold=True), w("| Beverages | Menu", 24, 10)] + rows_, [(0, 0, 800), (110, 20, 780), (300, 91, 471), (525, 0, 800)], src, 4)


def test_a_may_contain_or_a_nut_source_that_the_allergen_column_leaves_out_is_flagged():
    row = [w("Cake", 24, 150, bold=True), w("May", 140, 150), w("contain", 150, 150), w("NUTS", 165, 150)] + _figs(150) + [w("MILK", 735, 150, bold=True)]
    got = _page(FOOD, row)
    assert "treeNuts" in got[0]["flags"] and got[0]["milk"] == "Yes" and "milk" in got[0]["flags"]
    nuts = [w("Cake", 24, 150, bold=True), w("ALMONDS", 140, 150, bold=True)] + _figs(150) + [w("ALMONDS", 735, 150, bold=True)]
    assert "flags" not in _page(FOOD, nuts)[0]


def test_a_modifier_word_across_the_name_edge_and_a_tick_level_with_no_line_stop_the_run():
    src = {"name_x1": 134, "serving_x0": 134, "kcal_x0": 230, "marks_x0": 262, "markers": {"": "No"}, "labels": {"Milk": "milk"}, "gluten_from": []}
    chars = [{"text": c, "x0": 300, "x1": 306, "top": 100 + 7 * (3 - i), "bottom": 106 + 7 * (3 - i), "upright": False} for i, c in enumerate("Milk")]
    words = [{"text": "Cream", "x0": 24, "x1": 60, "top": 150, "bottom": 156, "size": 6, "fontname": "Bold", "upright": True},
             {"text": "per", "x0": 140, "x1": 150, "top": 150, "bottom": 156, "size": 6, "fontname": "Bold", "upright": True},
             {"text": "5", "x0": 236, "x1": 240, "top": 150, "bottom": 156, "size": 6, "fontname": "Regular", "upright": True},
             {"text": "kcal", "x0": 242, "x1": 252, "top": 150, "bottom": 156, "size": 6, "fontname": "Regular", "upright": True}]
    tick = {"x0": 297, "x1": 304, "top": 151, "bottom": 158}
    assert mm.parse_page(words, chars, [tick], src, 63)[0]["milk"] == "Yes"
    with pytest.raises(ValueError, match="level with no line"):
        mm.parse_page(words, chars, [{**tick, "top": 300, "bottom": 307}], src, 63)
    heading = [{"text": "DAIRY", "x0": 24, "x1": 50, "top": 130, "bottom": 136, "size": 6, "fontname": "Bold", "upright": True},
               {"text": "ALTERNATIVES", "x0": 116, "x1": 160, "top": 130, "bottom": 136, "size": 6, "fontname": "Bold", "upright": True}]
    assert mm.parse_page(heading + words, chars, [tick], src, 63)[0]["Category"] == "DAIRY ALTERNATIVES"   # a heading across the name edge is kept whole
    odd = words + [{"text": "stray", "x0": 300, "x1": 320, "top": 150, "bottom": 156, "size": 6, "fontname": "Regular", "upright": True}]
    with pytest.raises(ValueError, match="allergen columns"):
        mm.parse_page(odd, chars, [tick], src, 63)

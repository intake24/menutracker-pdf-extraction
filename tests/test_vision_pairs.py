from pathlib import Path

import pytest

from pipeline.llm import Budget, LlmError
from pipeline.parsers import vision_pairs as vp

FIELDS = {"p100_kcal": "energykCal_Per 100g/ml", "pp_kcal": "energykCal_Per Portion"}
SOURCE = {"fields": FIELDS, "joins": [{"matrix": [3], "nutrition": [4]}], "instructions": "x", "markers": {"✓": "Yes", "": ""},
          "tick_labels": {"Wheat": "wheat", "Egg / Egg Products": "egg", "Tree Nuts / Nut Derivatives": "treeNuts"}}
M = {"section": "DOUGHNUTS - RINGS", "name": "Original Glazed", "note": "", "vegetarian": "YES", "vegan": "NO", "halal": "YES",
     "ticks": ["Wheat"], "tree_nut_source": ""}
N = {"section": "DOUGHNUTS - RINGS", "name": "Original Glazed", "note": "", "weight": "51g", "p100_kcal": "384", "pp_kcal": "195"}


def test_a_pair_becomes_one_row_with_diet_allergens_and_figures():
    row = vp.join_rows([M], [N], SOURCE, 4)[0]
    assert (row["Product_Name"], row["Category"], row["source_page"], row["method"]) == ("Original Glazed", "DOUGHNUTS - RINGS", 4, "llm")
    assert (row["Suitable_for_Vegetarian"], row["Suitable_for_Vegan"], row["Suitable_for_Halal"]) == ("YES", "NO", "YES")
    assert row["wheat"] == "Yes" and "egg" not in row          # a blank cell is "not stated", not "No"
    assert (row["energykCal_Per 100g/ml"], row["energykCal_Per Portion"], row["Serving_Size"], row["Serving_Size_Unit"]) == ("384", "195", "51", "g")
    assert "flags" not in row


def test_a_note_under_the_name_and_a_tree_nut_source_are_kept():
    m = {**M, "note": "(NWD only)", "ticks": ["Tree Nuts / Nut Derivatives"], "tree_nut_source": "Hazelnut"}
    row = vp.join_rows([m], [{**N, "note": "(NWD only)"}], SOURCE, 4)[0]
    assert row["Product_Name"] == "Original Glazed (NWD only)" and row["treeNuts"] == "Yes" and row["treeNutSource"] == "Hazelnut"


def test_names_that_differ_are_flagged_not_merged_silently():
    row = vp.join_rows([{**M, "name": "Sprinkles"}], [{**N, "name": "Chocolate Sprinkles"}], SOURCE, 4)[0]
    assert row["Product_Name"] == "Chocolate Sprinkles" and "Sprinkles" in row["flags"] and row["flags"].startswith("warn:")
    with pytest.raises(LlmError, match="Pistachio"):
        vp.join_rows([{**M, "name": "Biscoff"}], [{**N, "name": "Pistachio Overload"}], SOURCE, 4)


def test_different_row_counts_stop_the_run():
    with pytest.raises(LlmError, match="1 rows, the nutrition .* 2 rows"):
        vp.join_rows([M], [N, N], SOURCE, 4)


def test_an_unknown_tick_label_or_unknown_diet_word_raises():
    with pytest.raises(LlmError, match="Peanut"):
        vp.join_rows([{**M, "ticks": ["Peanut"]}], [N], SOURCE, 4)
    with pytest.raises(LlmError, match="MAYBE"):
        vp.join_rows([{**M, "vegan": "MAYBE"}], [N], SOURCE, 4)


def test_figures_missing_on_a_nutrition_row_leave_columns_out():
    row = vp.join_rows([M], [{**N, "weight": "", "p100_kcal": "", "pp_kcal": ""}], SOURCE, 4)[0]
    assert "energykCal_Per Portion" not in row and "Serving_Size" not in row


def test_each_page_is_read_once_even_when_two_joins_use_it(tmp_path, monkeypatch):
    monkeypatch.setattr(vp.vision_table, "WORK", tmp_path)
    monkeypatch.setattr(vp, "WORK", tmp_path)
    monkeypatch.setattr(vp, "BUDGET", Budget())
    seen = []

    def runner(prompt, schema, add_dir):
        seen.append(prompt)
        rows = [M] if "tick" in prompt else [N]
        return {"is_error": False, "structured_output": {"rows": rows}, "total_cost_usd": 0.01}
    monkeypatch.setattr(vp, "RUNNER", runner)
    source = {**SOURCE, "joins": [{"matrix": [3], "nutrition": [4]}, {"matrix": [3], "nutrition": [5]}]}
    pdf = Path(__file__).resolve().parent.parent / "inputs" / "nutritional-information.pdf"
    rows = vp.parse(pdf, source)
    assert [r["source_page"] for r in rows] == [4, 5] and len(seen) == 3


def test_a_matrix_page_with_no_nutrition_page_gives_rows_with_diet_and_allergens_only():
    row = vp.matrix_only_rows([M], SOURCE, 26)[0]
    assert (row["Product_Name"], row["Category"], row["source_page"], row["wheat"]) == ("Original Glazed", "DOUGHNUTS - RINGS", 26, "Yes")
    assert "energykCal_Per Portion" not in row


def test_a_bracketed_note_or_a_size_is_not_a_difference_but_a_longer_name_is_flagged():
    row = vp.join_rows([{**M, "name": "Tea"}], [{**N, "name": "Tea (with oat milk) 12oz"}], SOURCE, 41)[0]
    assert row["Product_Name"] == "Tea (with oat milk) 12oz" and "flags" not in row
    row = vp.join_rows([{**M, "name": "Latte"}], [{**N, "name": "Latte made with Biscoff Sauce"}], SOURCE, 41)[0]
    assert row["flags"].startswith("warn:")


def _m(name, section="HOT", ticks=()):
    return {**M, "name": name, "section": section, "ticks": list(ticks)}


def _n(name, section="HOT", weight="340 ml"):
    return {**N, "name": name, "section": section, "weight": weight}


def test_by_name_gives_every_size_row_the_cells_of_its_allergen_row():
    matrix = [_m("Latte", ticks=["Wheat"]), _m("Mocha")]
    nutrition = [_n("Latte 12oz"), _n("Latte 16oz", weight="455 ml"), _n("Mocha 12oz")]
    rows = vp.join_rows(matrix, nutrition, SOURCE, 41, by_name=True)
    assert [r["Product_Name"] for r in rows] == ["Latte 12oz", "Latte 16oz", "Mocha 12oz"]
    assert [r.get("wheat") for r in rows] == ["Yes", "Yes", None]
    assert [r["Serving_Size"] for r in rows] == ["340", "455", "340"]


def test_by_name_ignores_a_bracketed_part_of_the_allergen_name():
    rows = vp.join_rows([_m("Pistachio Latte (with oat drink)")], [_n("Pistachio Latte 12oz")], SOURCE, 56, by_name=True)
    assert len(rows) == 1 and rows[0]["Product_Name"] == "Pistachio Latte 12oz"


def test_by_name_stops_on_a_nutrition_row_with_no_allergen_row_and_keeps_an_allergen_row_without_figures():
    with pytest.raises(LlmError, match="Chai"):
        vp.join_rows([_m("Latte")], [_n("Chai 12oz")], SOURCE, 41, by_name=True)
    rows = vp.join_rows([_m("Latte"), _m("Americano")], [_n("Latte 12oz")], SOURCE, 41, by_name=True)
    assert [r["Product_Name"] for r in rows] == ["Latte 12oz", "Americano"]
    assert rows[1]["flags"].startswith("warn:") and "Serving_Size" not in rows[1]


def test_a_join_can_pick_the_sections_of_its_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(vp, "WORK", tmp_path)
    monkeypatch.setattr(vp.vision_table, "WORK", tmp_path)
    monkeypatch.setattr(vp, "BUDGET", Budget())

    def runner(prompt, schema, add_dir):
        rows = ([_m("Latte", "LATTE (oat)", ["Wheat"]), _m("Latte", "LATTE (milk)")] if "tick" in prompt
                else [_n("Latte 12oz", "OAT DRINK"), _n("Latte 12oz", "SEMI SKIMMED MILK"), _n("Latte 12oz", "SKIMMED MILK")])
        return {"is_error": False, "structured_output": {"rows": rows}, "total_cost_usd": 0.01}
    monkeypatch.setattr(vp, "RUNNER", runner)
    source = {**SOURCE, "joins": [
        {"matrix": [3], "matrix_section": "oat", "nutrition": [4], "nutrition_section": "oat"},
        {"matrix": [3], "matrix_section": "milk", "nutrition": [4], "nutrition_section": "semi"},
        {"matrix": [3], "matrix_section": "milk", "nutrition": [4], "nutrition_section": r"(?<!semi )skimmed"}]}
    pdf = Path(__file__).resolve().parent.parent / "inputs" / "nutritional-information.pdf"
    rows = vp.parse(pdf, source)
    assert [(r["Category"], r.get("wheat")) for r in rows] == [("OAT DRINK", "Yes"), ("SEMI SKIMMED MILK", None), ("SKIMMED MILK", None)]
    with pytest.raises(LlmError, match="no nutrition rows with a section matching"):
        vp.parse(pdf, {**source, "joins": [{"matrix": [3], "nutrition": [4], "nutrition_section": "nothing like it"}]})


def test_a_join_can_pick_allergen_rows_by_name_when_the_kind_of_milk_is_in_the_name(tmp_path, monkeypatch):
    monkeypatch.setattr(vp, "WORK", tmp_path)
    monkeypatch.setattr(vp.vision_table, "WORK", tmp_path)
    monkeypatch.setattr(vp, "BUDGET", Budget())

    def runner(prompt, schema, add_dir):
        rows = [_m("Latte (with oat drink)", "PISTACHIO", ["Oat"]), _m("Latte (with milk)", "PISTACHIO")] if "tick" in prompt else [_n("Latte 12oz", "PISTACHIO")]
        return {"is_error": False, "structured_output": {"rows": rows}, "total_cost_usd": 0.01}
    monkeypatch.setattr(vp, "RUNNER", runner)
    source = {**SOURCE, "tick_labels": {**SOURCE["tick_labels"], "Oat": "oats"},
              "joins": [{"matrix": [3], "matrix_name": "milk", "nutrition": [4], "by_name": True},
                        {"matrix": [3], "matrix_name": "oat", "nutrition": []}]}
    pdf = Path(__file__).resolve().parent.parent / "inputs" / "nutritional-information.pdf"
    rows = vp.parse(pdf, source)
    assert "oats" not in rows[0] and rows[1]["oats"] == "Yes"


def test_by_name_stops_when_two_allergen_rows_have_the_same_name_core():
    matrix = [_m("Pistachio Latte (with oat drink)", ticks=["Wheat"]), _m("Pistachio Latte (with milk)")]
    with pytest.raises(LlmError, match="same name"):
        vp.join_rows(matrix, [_n("Pistachio Latte 12oz")], SOURCE, 56, by_name=True)


def test_a_size_is_only_ignored_at_the_end_of_a_name():
    assert vp._core("Latte 12oz") == vp._core("Latte") and vp._core("Bites 100g") != vp._core("Bites 200g")


def test_several_name_differences_in_one_join_look_like_a_shift_and_stop_the_run():
    matrix = [_m("Iced Latte"), _m("Iced Vanilla Latte"), _m("Iced Caramel Latte"), _m("Iced Chai Latte")]
    nutrition = [_n("Iced Vanilla Latte"), _n("Iced Caramel Latte"), _n("Iced Chai Latte"), _n("Iced Matcha Latte")]
    with pytest.raises(LlmError, match="shifted"):
        vp.join_rows(matrix, nutrition, SOURCE, 57)


def test_a_tree_nut_source_without_the_tick_is_flagged():
    row = vp.join_rows([{**M, "tree_nut_source": "Hazelnut"}], [N], SOURCE, 4)[0]
    assert row["treeNutSource"] == "Hazelnut" and "treeNuts" not in row and row["flags"].startswith("warn:")


def _runner_for(matrix, nutrition):
    def runner(prompt, schema, add_dir):
        return {"is_error": False, "structured_output": {"rows": matrix if "tick" in prompt else nutrition}, "total_cost_usd": 0.01}
    return runner


def _setup(monkeypatch, tmp_path, matrix, nutrition):
    monkeypatch.setattr(vp, "WORK", tmp_path)
    monkeypatch.setattr(vp.vision_table, "WORK", tmp_path)
    monkeypatch.setattr(vp, "BUDGET", Budget())
    monkeypatch.setattr(vp, "RUNNER", _runner_for(matrix, nutrition))
    return Path(__file__).resolve().parent.parent / "inputs" / "nutritional-information.pdf"


def test_an_allergen_row_without_figures_is_kept_once_however_many_joins_select_it(tmp_path, monkeypatch):
    pdf = _setup(monkeypatch, tmp_path, [_m("Latte", "A"), _m("Americano", "A")], [_n("Latte 12oz", "X"), _n("Latte 12oz", "Y")])
    source = {**SOURCE, "joins": [{"matrix": [3], "nutrition": [4], "nutrition_section": "X", "by_name": True},
                                  {"matrix": [3], "nutrition": [4], "nutrition_section": "Y", "by_name": True}]}
    names = [r["Product_Name"] for r in vp.parse(pdf, source)]
    assert sorted(names) == ["Americano", "Latte 12oz", "Latte 12oz"]


def test_a_row_that_no_join_selects_stops_the_run(tmp_path, monkeypatch):
    pdf = _setup(monkeypatch, tmp_path, [_m("Latte", "A")], [_n("Latte 12oz", "X"), _n("Latte 12oz", "OTHER")])
    source = {**SOURCE, "joins": [{"matrix": [3], "nutrition": [4], "nutrition_section": "X", "by_name": True}]}
    with pytest.raises(LlmError, match="no join"):
        vp.parse(pdf, source)


def test_a_pdf_name_with_dots_still_gives_its_page_image(tmp_path, monkeypatch):
    monkeypatch.setattr(vp.vision_table, "WORK", tmp_path)
    monkeypatch.setattr(vp, "WORK", tmp_path)
    monkeypatch.setattr(vp, "BUDGET", Budget())
    monkeypatch.setattr(vp, "RUNNER", lambda prompt, schema, add_dir: {"is_error": False, "structured_output": {"rows": [M]}, "total_cost_usd": 0.0})
    pdf = Path(__file__).resolve().parent.parent / "inputs" / "04.25-BK-Core-Menu-PB2.pdf"
    assert vp.raw_rows(pdf, {"joins": [{"matrix": [1], "nutrition": []}], "instructions": "x"}, 1)[0]["name"] == "Original Glazed"
    assert (tmp_path / "pages" / "04.25-BK-Core-Menu-PB2-1.png").exists()

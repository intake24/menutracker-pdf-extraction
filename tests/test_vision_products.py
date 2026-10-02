from pathlib import Path

import pytest

from pipeline.llm import Budget, LlmError
from pipeline.parsers import vision_products as vp

HEADERS = {"PER 100G / ENERGY kcal": "energykCal_Per 100g/ml", "PER 100G / PROTEIN g": "protein_Per 100g/ml",
           "PER SLICE / PORTION SIZE g": "Serving_Size|g", "PER SLICE / TOTAL SLICES": "Total_Slices"}
SOURCE = {"header_columns": HEADERS, "markers": {"": "No"}, "pages": ["2-3", 5], "instructions": "x"}
ITEM = {"section": "PIZZAS", "name": "DOUBLE PEPPERONI", "variant": "Original Base - Medium",
        "values": {"PER 100G / ENERGY kcal": "299", "PER 100G / PROTEIN g": "", "PER SLICE / PORTION SIZE g": "94",
                   "PER SLICE / TOTAL SLICES": "8"}, "contains": "Gluten, Wheat, Milk", "may": "None"}


def test_pages_expand_from_numbers_and_ranges():
    assert vp.expand_pages(["2-4", 7]) == [2, 3, 4, 7]


def test_a_row_maps_headers_to_columns_units_and_allergens():
    row = vp.rows_from_answer({"rows": [ITEM]}, SOURCE, 12)[0]
    assert row["Product_Name"] == "DOUBLE PEPPERONI" and row["Size"] == "Original Base - Medium" and row["Category"] == "PIZZAS"
    assert (row["energykCal_Per 100g/ml"], row["Serving_Size"], row["Serving_Size_Unit"], row["Total_Slices"]) == ("299", "94", "g", "8")
    assert "protein_Per 100g/ml" not in row                      # a blank cell stays blank
    assert (row["gluten"], row["wheat"], row["milk"], row["egg"]) == ("Yes", "Yes", "Yes", "No") and row["method"] == "llm"


def test_a_row_without_allergen_text_has_no_allergen_cells():
    row = vp.rows_from_answer({"rows": [{**ITEM, "contains": "", "may": ""}]}, {**SOURCE, "markers": {"": ""}}, 1)[0]
    assert "gluten" not in row or row["gluten"] == ""


def test_an_unknown_header_and_a_missing_name_raise():
    bad = {**ITEM, "values": {"PER 100G / SODIUM g": "1"}}
    with pytest.raises(LlmError, match="PER 100G / SODIUM g"):
        vp.rows_from_answer({"rows": [bad]}, SOURCE, 3)
    with pytest.raises(LlmError, match="without a name"):
        vp.rows_from_answer({"rows": [{**ITEM, "name": ""}]}, SOURCE, 3)


def test_each_listed_page_is_one_call(tmp_path, monkeypatch):
    monkeypatch.setattr(vp, "WORK", tmp_path)
    monkeypatch.setattr(vp, "BUDGET", Budget())
    seen = []

    def runner(prompt, schema, add_dir):
        seen.append(prompt)
        return {"is_error": False, "structured_output": {"rows": [ITEM]}, "total_cost_usd": 0.01}
    monkeypatch.setattr(vp, "RUNNER", runner)
    pdf = Path(__file__).resolve().parent.parent / "inputs" / "nutritional-information.pdf"
    rows = vp.parse(pdf, SOURCE)
    assert [r["source_page"] for r in rows] == [2, 3, 5] and len(seen) == 3


def test_headers_match_in_any_case_and_a_target_can_set_the_portion_type():
    source = {**SOURCE, "header_columns": {"PER SLICE / PORTION SIZE Slice": "Portion_Size@Slice", "PER 100G / ENERGY kcal": "energykCal_Per 100g/ml"}}
    item = {**ITEM, "values": {"per slice / portion size SLICE": "1", "PER 100G / ENERGY Kcal": "299"}}
    row = vp.rows_from_answer({"rows": [item]}, source, 1)[0]
    assert (row["Portion_Size"], row["Portion_Type"], row["energykCal_Per 100g/ml"]) == ("1", "Slice", "299")


def test_a_qualified_allergen_applies_only_to_the_named_rows():
    text = "Gluten, Wheat, Soya. With Gluten Free Oats – Vegan Stuffed Crust Only"
    stuffed = vp.rows_from_answer({"rows": [{**ITEM, "variant": "Stuffed Crust - Large", "contains": text, "may": ""}]}, SOURCE, 1)[0]
    thin = vp.rows_from_answer({"rows": [{**ITEM, "variant": "Original Base - Large", "contains": text, "may": ""}]}, SOURCE, 1)[0]
    assert (stuffed["oats"], thin["oats"]) == ("Yes", "No") and stuffed["gluten"] == thin["gluten"] == "Yes"


def test_a_printed_row_warning_makes_the_named_cells_may_contain_and_never_lowers_a_yes():
    source = {**SOURCE, "rules": [{"variant_has": "Wheat Free", "may_contain": ["gluten", "wheat"]}]}
    wheat_free = {**ITEM, "variant": "Wheat Free Stone Baked *- Medium", "contains": "Milk", "may": "None"}
    row = vp.rows_from_answer({"rows": [wheat_free]}, source, 1)[0]
    assert (row["gluten"], row["wheat"], row["milk"]) == ("May contain", "May contain", "Yes")
    assert vp.rows_from_answer({"rows": [{**wheat_free, "contains": "Gluten, Wheat"}]}, source, 1)[0]["wheat"] == "Yes"
    assert vp.rows_from_answer({"rows": [ITEM]}, source, 1)[0]["wheat"] == "Yes"   # other rows are untouched


def test_a_qualified_allergen_on_a_row_with_no_variant_raises():
    text = "Gluten, Wheat, Soya. With Gluten Free Oats – Vegan Stuffed Crust Only"
    with pytest.raises(LlmError, match="without a variant"):
        vp.rows_from_answer({"rows": [{**ITEM, "variant": "", "contains": text}]}, SOURCE, 1)


def test_all_model_parsers_share_one_budget():
    from pipeline import llm
    from pipeline.parsers import vision_table
    assert vp.BUDGET is vision_table.BUDGET is llm.BUDGET


def test_a_page_with_crops_is_read_band_by_band(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(vp, "WORK", tmp_path)
    monkeypatch.setattr(vp, "BUDGET", Budget())
    seen = []

    def runner(prompt, schema, add_dir):
        seen.append(prompt)
        return {"is_error": False, "structured_output": {"rows": [{**ITEM, "name": f"Pizza {len(seen)}"}]}, "total_cost_usd": 0.01}
    monkeypatch.setattr(vp, "RUNNER", runner)
    pdf = Path(__file__).resolve().parent.parent / "inputs" / "nutrition_pizzas.pdf"
    rows = vp.parse(pdf, {**SOURCE, "pages": [2], "crops": {2: [[60, 300], [300, 700]]}})
    assert [r["Product_Name"] for r in rows] == ["Pizza 1", "Pizza 2"] and len(seen) == 2
    assert "crop1" in seen[0] and "crop2" in seen[1]


def test_a_variant_can_be_split_into_cheese_crust_and_size():
    source = {**SOURCE, "variant_columns": True}
    one = vp.rows_from_answer({"rows": [{**ITEM, "variant": "Standard Mozzarella - Classic Crust - Large"}]}, source, 1)[0]
    two = vp.rows_from_answer({"rows": [{**ITEM, "variant": "Standard Mozzarella - Small"}]}, source, 1)[0]
    assert (one["Cheese"], one["Crust"], one["Size"]) == ("Standard Mozzarella", "Classic Crust", "Large")
    assert (two["Cheese"], two["Size"]) == ("Standard Mozzarella", "Small") and "Crust" not in two
    with pytest.raises(LlmError, match="parts"):
        vp.rows_from_answer({"rows": [{**ITEM, "variant": "a - b - c - d"}]}, source, 1)


def test_text_figures_replace_the_models_and_a_size_disagreement_stops_the_run(monkeypatch):
    from pathlib import Path
    import pipeline.parsers.grouped_table as gt
    spec = {"columns": ["a", "b"], "size_x0": 1, "size_order": ["Small"]}
    monkeypatch.setattr(gt, "figure_lines", lambda *args: [("Small", {"a": "1", "b": "2"})])
    rows = [{"Product_Name": "X", "Size": "Small", "a": "9"}]
    out = vp.with_text_figures(Path("x.pdf"), {"figures_from_text": spec}, 2, rows)
    assert (out[0]["a"], out[0]["b"]) == ("1", "2")
    with pytest.raises(LlmError, match="size"):
        vp.with_text_figures(Path("x.pdf"), {"figures_from_text": spec}, 2, [{"Product_Name": "X", "Size": "Large"}])
    with pytest.raises(LlmError, match="2 rows"):
        vp.with_text_figures(Path("x.pdf"), {"figures_from_text": spec}, 2, rows * 2)


def test_a_label_the_model_misread_is_replaced_by_the_printed_one_and_flagged(monkeypatch):
    from pathlib import Path

    from pipeline.ingest import Word
    import pipeline.ingest as ing
    monkeypatch.setattr(ing, "page_words", lambda pdf: [[Word(0, 0, 1, 1, t) for t in "Plant-Based Margheri-tastic Medium".split()]])
    rows = [{"Product_Name": "Plant-Based Margherita-tastic"}, {"Product_Name": "Plant-Based Margheri-tastic"}]
    out = vp.snap_labels(Path("x.pdf"), 1, rows, ["Product_Name"])
    assert out[0]["Product_Name"] == "Plant-Based Margheri-tastic" and "Margherita-tastic" in out[0]["flags"] and "flags" not in out[1]
    with pytest.raises(LlmError, match="not printed"):
        vp.snap_labels(Path("x.pdf"), 1, [{"Product_Name": "Hawaiian Special Deluxe"}], ["Product_Name"])

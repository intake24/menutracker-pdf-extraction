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

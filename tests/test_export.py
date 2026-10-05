import csv

from pipeline.columns import PROVENANCE, load_columns
from pipeline.export import finalise, write_csv


def test_finalise_flags_without_changing_values_then_write(tmp_path):
    columns = load_columns()
    rows = [
        {"Product_Name": "Toast", "energykJ_Per Portion": "393", "energykCal_Per Portion": "93",
         "milk": "Yes", "egg": "No", "region": "UK", "source_page": 2},
        {"Product_Name": "Jam", "egg": "N", "fat_Per Portion": "1", "saturates_Per Portion": "2",
         "region": "UK", "source_page": 3, "flags": "error: no nutrition line found"},
    ]
    out = finalise(rows, columns)
    assert out[0]["flags"] == "" and out[0]["energykCal_Per Portion"] == "93"
    assert "no nutrition line found" in out[1]["flags"]
    assert "saturates > fat" in out[1]["flags"] and "egg" in out[1]["flags"]
    assert out[1]["egg"] == "N"   # invalid values are kept for the reviewer, never silently changed

    header = write_csv(out, columns, tmp_path / "16_Test.csv")
    assert header == ["Product_Name", "energykCal_Per Portion", "energykJ_Per Portion", "fat_Per Portion",
                      "saturates_Per Portion", "egg", "milk", *PROVENANCE]  # only columns with a value
    with (tmp_path / "16_Test.csv").open(newline="") as f:
        written = list(csv.DictReader(f))
    assert written[0]["egg"] == "No" and written[0]["source_page"] == "2" and written[1]["milk"] == ""


def test_unknown_column_stops_the_run():
    import pytest
    with pytest.raises(ValueError, match="energykJ_Per Serving"):
        finalise([{"Product_Name": "x", "energykJ_Per Serving": "100"}], load_columns())


def test_merge_by_key_joins_rows_of_one_product_with_no_overlapping_cells():
    from pipeline.export import merge_by_key
    allergens = {"Product_Name": "Fries", "Category": "Sides", "region": "UK", "source_page": 2, "method": "parser", "wheat": "Yes", "flags": "warn: a"}
    nutrition = {"Product_Name": "Fries", "Category": "Sides", "region": "UK", "source_page": 17, "method": "parser", "energykCal_Per Portion": "384", "flags": "warn: b"}
    other = {"Product_Name": "Cola", "Category": "Drinks", "region": "UK", "source_page": 6, "method": "parser", "milk": ""}
    rows = merge_by_key([allergens, other, nutrition])
    assert len(rows) == 2 and rows[0]["wheat"] == "Yes" and rows[0]["energykCal_Per Portion"] == "384"
    assert rows[0]["source_page"] == 2 and rows[0]["flags"] == "warn: a | warn: b" and rows[1]["Product_Name"] == "Cola"


def test_merge_by_key_leaves_rows_apart_when_a_cell_is_in_both_or_the_key_differs():
    from pipeline.export import merge_by_key
    a = {"Product_Name": "Fries", "Category": "Sides", "region": "UK", "wheat": "Yes"}
    assert len(merge_by_key([a, {**a, "wheat": "No"}])) == 2                      # same cell, two values
    assert len(merge_by_key([a, {**a, "Category": "Kids", "milk": "Yes"}])) == 2  # another category
    assert len(merge_by_key([a, {**a, "region": "NI", "milk": "Yes"}])) == 2      # another region
    assert len(merge_by_key([{**a, "Size": "Large"}, {**a, "milk": "Yes"}])) == 2  # another size

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


def _row(name, category, page, **cells):
    return {"Product_Name": name, "Category": category, "region": "UK", "source_page": page, "method": "parser", **cells}


def test_merge_joins_one_to_one_matches_and_leaves_a_remark_for_data_users():
    from pipeline.export import merge_by_key
    allergens = _row("Fries", "Sides", 2, wheat="Yes", flags="warn: a")
    nutrition = _row("Fries", "Sides", 17, **{"energykCal_Per Portion": "384", "flags": "warn: b"})
    other = _row("Cola", "Drinks", 6, milk="")
    rows = merge_by_key([allergens, other, nutrition])
    assert len(rows) == 2 and rows[0]["wheat"] == "Yes" and rows[0]["energykCal_Per Portion"] == "384"
    assert rows[0]["source_page"] == "2, 17" and rows[0]["flags"] == "warn: a | warn: b" and rows[1]["Product_Name"] == "Cola"
    assert rows[0]["notes"].startswith("Merged product: ") and "pages 2, 17" in rows[0]["notes"] and "notes" not in rows[1]


def test_the_remark_is_added_to_existing_notes_and_names_a_different_heading():
    from pipeline.export import merge_by_key
    a = _row("Tomato Pasta", "Buffet Sides", 5, wheat="Yes", notes="Barley <20ppm")
    b = _row("Tomato Pasta", "Buffet Sides - Buffet Pasta", 23, **{"energykCal_Per Portion": "100"})
    row = merge_by_key([a, b])[0]
    assert row["notes"].startswith("Barley <20ppm; Merged product: ") and "'Buffet Sides'" in row["notes"] and "'Buffet Sides - Buffet Pasta'" in row["notes"]


def test_headings_that_differ_only_in_punctuation_or_in_depth_are_the_same_heading():
    from pipeline.export import merge_by_key
    assert len(merge_by_key([_row("Sour Cream", "Dine In Dip Pots", 2, egg="Yes"), _row("Sour Cream", "Dine-in Dip Pots", 18, **{"energykCal_Per Portion": "9"})])) == 1


def test_similar_but_different_things_stay_separate():
    from pipeline.export import merge_by_key
    a = _row("Pepperoni", "Pizza Toppings", 3, milk="May contain")
    assert len(merge_by_key([a, _row("Pepperoni", "Pizza", 18, **{"energykCal_Per Slice": "181"})])) == 2           # a heading that only starts with the other
    assert len(merge_by_key([a, _row("Pepperoni Feast", "Pizza Toppings", 18, **{"energykCal_Per Slice": "1"})])) == 2   # another name
    assert len(merge_by_key([a, _row("Pepperoni", "Pizza Toppings", 18, **{"energykCal_Per Slice": "1"}, region="NI")])) == 2
    assert len(merge_by_key([_row("Fries", "Sides", 2, wheat="Yes"), _row("Fries", "Sides", 17, Size="Large")])) == 2
    assert len(merge_by_key([a, _row("Pepperoni", "Pizza Toppings", 18, milk="Yes")])) == 2                              # the same cell in both


def test_a_name_printed_twice_is_not_merged_because_the_pairing_would_be_a_guess():
    from pipeline.export import merge_by_key
    adult = _row("Fries", "Sides", 17, **{"energykCal_Per Portion": "384"})
    kids = _row("Fries", "Sides", 23, **{"energykCal_Per Portion": "209"})
    assert len(merge_by_key([adult, kids, _row("Fries", "Sides", 2, wheat="Yes"), _row("Fries", "Sides", 5, wheat="Yes")])) == 4

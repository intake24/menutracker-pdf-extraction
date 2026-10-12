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
    assert header == ["item_name", "kcal", "kj", "fat", "satfat", "egg", "milk", *PROVENANCE]  # only columns with a value, template columns under their standard heading
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


def _fin(**cells):
    return finalise([{"Product_Name": "x", "region": "UK", "source_page": 1, **cells}], load_columns())[0]


def test_a_decimal_comma_becomes_a_point_in_nutrient_cells_and_the_change_is_flagged():
    r = _fin(**{"salt_Per 100g/ml": "1,75", "fat_Per Portion": "<0,005"})
    assert (r["salt_Per 100g/ml"], r["fat_Per Portion"]) == ("1.75", "<0.005")
    assert "warn: normalised salt_Per 100g/ml '1,75' to '1.75'" in r["flags"] and "error" not in r["flags"]


def test_a_thousands_comma_in_an_energy_cell_is_removed_but_other_commas_there_are_left_for_review():
    r = _fin(**{"energykJ_Per 100g/ml": "1,702", "energykCal_Per 100g/ml": "408"})
    assert r["energykJ_Per 100g/ml"] == "1702" and "kJ/kcal mismatch" not in r["flags"]   # the check now sees the real figure
    r = _fin(**{"energykJ_Per Portion": "1,2"})
    assert r["energykJ_Per Portion"] == "1,2" and "error" in r["flags"]


def test_g_and_mg_are_removed_from_nutrient_numbers_and_the_change_is_flagged():
    r = _fin(**{"fibre_Per Portion": "2.7g", "fat_Per Portion": "<0.5 g", "protein_Per 100g/ml": "0g", "sodium_Per Portion": "108mg",
                "salt_Per Portion": "1,5g"})
    assert (r["fibre_Per Portion"], r["fat_Per Portion"], r["protein_Per 100g/ml"], r["sodium_Per Portion"], r["salt_Per Portion"]) == \
        ("2.7", "<0.5", "0", "108", "1.5")
    assert "warn: normalised sodium_Per Portion '108mg' to '108'" in r["flags"] and "error" not in r["flags"]


def test_other_units_and_markers_in_nutrient_cells_stay_and_are_flagged():
    r = _fin(**{"energykCal_Per Portion": "40kcal", "zinc_Per Portion": "5 µg", "sugars_Per Portion": "*", "carbohydrates_Per Portion": "#N/A"})
    assert (r["energykCal_Per Portion"], r["zinc_Per Portion"], r["sugars_Per Portion"], r["carbohydrates_Per Portion"]) == ("40kcal", "5 µg", "*", "#N/A")
    assert r["flags"].count("error") == 4


def test_other_cells_are_not_touched_by_the_clean_ups():
    r = _fin(**{"Product_Name": "1,5 g burger", "fibre_Per Portion": "Trace", "salt_Per Portion": "#N/A", "notes": "0g, 1/2"})
    assert (r["Product_Name"], r["fibre_Per Portion"], r["salt_Per Portion"], r["notes"]) == ("1,5 g burger", "Trace", "#N/A", "0g, 1/2")


def test_recommended_portions_fractions_become_decimals():
    assert _fin(Recommended_Portions="1/2")["Recommended_Portions"] == "0.5"
    r = _fin(Recommended_Portions="1/4")
    assert r["Recommended_Portions"] == "0.25" and "warn: normalised Recommended_Portions '1/4' to '0.25'" in r["flags"]
    assert _fin(Recommended_Portions="2")["Recommended_Portions"] == "2"


def test_drop_rows_removes_the_named_products_only():
    from pipeline.export import drop_rows
    rows = [{"Product_Name": "Swap chips"}, {"Product_Name": "Chips"}]
    assert drop_rows(rows, ["Swap chips"]) == [{"Product_Name": "Chips"}]
    assert drop_rows(rows, []) == rows


def test_write_csv_uses_the_research_teams_standard_headings_and_read_output_maps_them_back(tmp_path):
    from pipeline.evaluate import read_output
    columns = load_columns()
    rows = [{"Product_Name": "Toast", "Category": "BREAKFAST", "Size": "Large", "energykCal_Per Portion": "93", "fat_Per 100g/ml": "1",
             "sodium_Per Portion": "10", "milk": "Yes", "region": "UK", "source_page": 2}]
    header = write_csv(finalise(rows, columns), columns, tmp_path / "16_Test.csv")
    assert header == ["item_name", "Size", "menu_section", "fat_100", "kcal", "sodium_Per Portion", "milk", *PROVENANCE]   # no template name: unchanged
    back = read_output(tmp_path / "16_Test.csv")[0]
    assert back["Product_Name"] == "Toast" and back["energykCal_Per Portion"] == "93" and back["fat_Per 100g/ml"] == "1" and back["Size"] == "Large"
    assert "kcal" not in back and "item_name" not in back


def test_read_output_also_reads_a_file_that_still_has_our_own_headings(tmp_path):
    from pipeline.evaluate import read_output
    (tmp_path / "g.csv").write_text("Product_Name,energykCal_Per Portion\nToast,93\n")
    assert read_output(tmp_path / "g.csv") == [{"Product_Name": "Toast", "energykCal_Per Portion": "93"}]

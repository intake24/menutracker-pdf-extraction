from pipeline.evaluate import compare_golden, compare_ground_truth, ground_truth_file, read_csv, same

MAPPING = {"item_name": "Product_Name", "kcal": "energykCal_Per Portion", "fat": "fat_Per Portion"}
OURS = [{"Product_Name": "Sweet Popcorn", "Size": "Large", "energykCal_Per Portion": "958.9", "fat_Per Portion": "Negligible"},
        {"Product_Name": "Croissant", "Size": "", "energykCal_Per Portion": "167", "fat_Per Portion": "7.7"}]


def test_same_compares_numbers_as_numbers_and_words_case_insensitively():
    assert same("7.70", "7.7") and same("Negligible", "negligible") and not same("7.7", "7.8")


def test_ground_truth_file_prefers_corrected_version(tmp_path):
    (tmp_path / "Odeon" / "Previous").mkdir(parents=True)
    for p in ["Odeon/menu.csv", "Odeon/menu_v0.1.csv", "Odeon/Previous/menu.csv"]:
        (tmp_path / p).write_text("item_name\n")
    assert ground_truth_file(tmp_path, "menu") == tmp_path / "Odeon" / "menu_v0.1.csv"
    assert ground_truth_file(tmp_path, "other") is None


def test_ground_truth_file_ignores_soft_hyphens_and_escaped_spaces(tmp_path):
    (tmp_path / "Dominos").mkdir()
    (tmp_path / "Dominos" / "nutrition_pizzas\u00ad_v0.1.csv").write_text("item_name\n")
    (tmp_path / "Dominos" / "my_20menu.csv").write_text("item_name\n")
    assert ground_truth_file(tmp_path, "nutrition_pizzas").name == "nutrition_pizzas\u00ad_v0.1.csv"
    assert ground_truth_file(tmp_path, "my%20menu").name == "my_20menu.csv"


def test_rows_match_on_name_plus_size_and_cells_compare():
    truth = [{"item_name": "Sweet Popcorn - Large", "kcal": "958.9", "fat": "Negligible"},
             {"item_name": "Croissant", "kcal": "167", "fat": "7.7"}]
    r = compare_ground_truth(truth, OURS, MAPPING, set())
    assert r["passed"] and r["recall"] == 1.0 and r["cells"] == 4


def test_mismatch_and_unmatched_fail_unless_in_errata():
    truth = [{"item_name": "Croissant", "kcal": "176", "fat": "7.7"}, {"item_name": "Ghost Bun", "kcal": "1", "fat": "1"}]
    r = compare_ground_truth(truth, OURS, MAPPING, set())
    assert not r["passed"] and r["unmatched"] == ["Ghost Bun"]
    assert r["mismatches"] == ["Croissant.kcal: Pearl Scan '176', ours '167'"]
    r = compare_ground_truth(truth, OURS, MAPPING, {("Croissant", "kcal"), ("Ghost Bun", "*")})
    assert r["passed"] and r["rows"] == 1


def test_golden_rows_must_match_exactly():
    golden = [{"Product_Name": "Croissant", "Category": "BAKERY", "milk": "Yes"}]
    ours = [{"Product_Name": "Croissant", "Category": "BAKERY", "milk": "May contain"}]
    assert compare_golden(golden, ours) == ["Croissant.milk: expected 'Yes', got 'May contain'"]
    assert compare_golden(golden, []) == ["missing row: Croissant (BAKERY)"]


def test_blank_golden_cell_matches_a_column_the_chain_csv_left_out():
    golden = [{"Product_Name": "Croissant", "Category": "BAKERY", "spelt": "", "milk": "Yes"}]
    ours = [{"Product_Name": "Croissant", "Category": "BAKERY", "milk": "Yes"}]
    assert compare_golden(golden, ours) == []
    assert compare_golden([golden[0] | {"spelt": "No"}], ours) == ["Croissant: column 'spelt' not in output"]


def test_read_csv_falls_back_to_windows_1252(tmp_path):
    from pipeline.evaluate import read_csv
    path = tmp_path / "pearl.csv"
    path.write_bytes("item_name,kcal\nJalapeño Peppers,4\n".encode("cp1252"))
    assert read_csv(path) == [{"item_name": "Jalapeño Peppers", "kcal": "4"}]
    path.write_bytes("item_name,kcal\nJalapeño Peppers,4\n".encode("utf-8-sig"))
    assert read_csv(path)[0]["item_name"] == "Jalapeño Peppers"


def test_repeated_names_pair_up_by_order_of_occurrence():
    truth = [{"item_name": "Margherita", "kcal": "100"}, {"item_name": "Margherita", "kcal": "200"}]
    ours = [{"Product_Name": "Margherita", "Size": "", "energykCal_Per Portion": "100"},
            {"Product_Name": "Margherita", "Size": "", "energykCal_Per Portion": "200"}]
    mapping = {"item_name": "Product_Name", "kcal": "energykCal_Per Portion"}
    assert compare_ground_truth(truth, ours, mapping, set())["passed"]
    swapped = compare_ground_truth(truth, ours[::-1], mapping, set())
    assert not swapped["passed"] and len(swapped["mismatches"]) == 2
    lost = compare_ground_truth(truth, ours[:1], mapping, set())
    assert lost["unmatched"] == ["Margherita"] and not lost["passed"]


def test_read_csv_handles_a_file_mixing_windows_1252_and_utf8_lines(tmp_path):
    path = tmp_path / "mixed.csv"
    path.write_bytes("item_name\nCr\u00e8me\n".encode("cp1252") + "BACARD\u00cd\n".encode("utf-8"))
    assert [r["item_name"] for r in read_csv(path)] == ["Cr\u00e8me", "BACARD\u00cd"]


def test_every_ground_truth_column_is_in_the_pearl_scan_column_map():
    import glob
    from pathlib import Path

    import yaml
    root = Path(__file__).resolve().parent.parent
    mapping = yaml.safe_load((root / "config" / "pearlscan_columns.yaml").read_text())
    missing = set()
    for f in glob.glob(str(root / "inputs" / "ground-truth" / "**" / "*.csv"), recursive=True):
        if "Previous" not in f:
            missing |= set(read_csv(Path(f))[0]) - set(mapping)
    assert not missing


def test_columns_mapped_to_nothing_are_not_compared():
    truth = [{"item_name": "Croissant", "kcal": "167", "serves": "2"}]
    r = compare_ground_truth(truth, OURS, {"item_name": "Product_Name", "kcal": "energykCal_Per Portion", "serves": None}, set())
    assert r["passed"] and r["cells"] == 1


def test_a_row_printed_per_100g_matches_pearl_scans_100g_serving():
    truth = [{"item_name": "Whipped Cream", "servingsize": "100", "servingsizeunit": "g", "kcal": "336"}]
    mapping = {"item_name": "Product_Name", "servingsize": "Serving_Size", "servingsizeunit": "Serving_Size_Unit",
               "kcal": "energykCal_Per Portion"}
    ours = [{"Product_Name": "Whipped Cream", "Size": "", "energykCal_Per 100g/ml": "336"}]
    r = compare_ground_truth(truth, ours, mapping, set())
    assert r["passed"] and r["cells"] == 1
    ours[0]["energykCal_Per 100g/ml"] = "337"
    assert not compare_ground_truth(truth, ours, mapping, set())["passed"]


def test_the_per_100g_rule_does_not_excuse_a_row_that_also_has_per_portion_values():
    truth = [{"item_name": "Pizza", "servingsize": "100", "servingsizeunit": "g", "kcal": "250"}]
    mapping = {"item_name": "Product_Name", "servingsize": "Serving_Size", "kcal": "energykCal_Per Portion"}
    ours = [{"Product_Name": "Pizza", "Size": "", "energykCal_Per Portion": "900", "energykCal_Per 100g/ml": "250"}]
    r = compare_ground_truth(truth, ours, mapping, set())
    assert not r["passed"] and len(r["mismatches"]) == 2


def test_a_pearl_scan_name_that_is_the_start_of_ours_without_notes_still_matches_when_cells_agree():
    mapping = {"item_name": "Product_Name", "kcal": "energykCal_Per Portion"}
    ours = [{"Product_Name": "Tango Raspberry - Regular (16oz as served) *Not for children", "Size": "", "energykCal_Per Portion": "59"},
            {"Product_Name": "Popcorn Topper - Contain E Numbers which may affect", "Size": "", "energykCal_Per Portion": "67"}]
    truth = [{"item_name": "Tango Raspberry Regular", "kcal": "59"}, {"item_name": "Popcorn Topper", "kcal": "67"}]
    assert compare_ground_truth(truth, ours, mapping, set())["passed"]
    truth[0]["kcal"] = "58"   # a prefix match still compares every cell
    r = compare_ground_truth(truth, ours, mapping, set())
    assert not r["passed"] and r["unmatched"] == []
    r = compare_ground_truth([{"item_name": "Cola", "kcal": "1"}], ours, mapping, set())
    assert r["unmatched"] == ["Cola"]

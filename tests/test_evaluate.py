from pipeline.evaluate import compare_golden, compare_ground_truth, ground_truth_file, same

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

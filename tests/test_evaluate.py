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

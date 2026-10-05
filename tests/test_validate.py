from pipeline.validate import check_row, duplicate_issues


def portion(**nutrients):
    return {f"{k}_Per Portion": v for k, v in nutrients.items()}


CROISSANT = portion(energykJ="698", energykCal="167", fat="7.7", saturates="4.4",
                    carbohydrates="19.9", sugars="2.3", protein="3.8")


def test_clean_row():
    assert check_row(CROISSANT) == []


def test_kj_kcal_mismatch():
    assert any(i.startswith("error: kJ/kcal") for i in check_row(CROISSANT | portion(energykJ="900")))


def test_subset_errors():
    issues = check_row(CROISSANT | portion(saturates="8.0", sugars="25"))
    assert any("saturates > fat" in i for i in issues)
    assert any("sugars > carbohydrates" in i for i in issues)


def test_atwater_is_warning_only():
    issues = check_row(CROISSANT | portion(energykCal="300", energykJ="1255"))
    assert len(issues) == 1 and issues[0].startswith("warn: Atwater")


def test_tiny_values_no_false_alarm():
    sachet = portion(energykJ="16", energykCal="4", fat="0.0", saturates="0.0",
                     carbohydrates="0.9", sugars="0.0", protein="0.0")
    assert check_row(sachet) == []


def test_text_values_skip_arithmetic():
    assert check_row(CROISSANT | portion(fat="Negligible", saturates="Trace")) == []


def test_other_bases_checked():
    assert check_row({"energykJ_Per 100g/ml": "900", "energykCal_Per 100g/ml": "100"})


def test_duplicates():
    a = {"Product_Name": "Toast", "Category": "BAKERY", "energykCal_Per Portion": "90", "source_page": 1}
    assert duplicate_issues([a, a | {"source_page": 3}]) == {}
    assert list(duplicate_issues([a, a | {"energykCal_Per Portion": "95"}])) == [1]
    assert duplicate_issues([a | {"region": "UK"}, a | {"region": "NI", "energykCal_Per Portion": "95"}]) == {}


def test_rows_that_differ_in_cheese_or_crust_are_not_duplicates():
    from pipeline.validate import duplicate_issues
    base = {"Product_Name": "American Hot", "Category": "", "Size": "Large", "region": "UK", "energykCal_Per Pizza": "1"}
    rows = [base | {"Cheese": "Standard Mozzarella", "Crust": "Classic Crust"},
            base | {"Cheese": "Standard Mozzarella", "Crust": "Stuffed Crust", "energykCal_Per Pizza": "2"},
            base | {"Cheese": "Reduced Fat Mozzarella", "Crust": "Classic Crust", "energykCal_Per Pizza": "3"}]
    assert duplicate_issues(rows) == {}
    rows[1]["Crust"] = "Classic Crust"; rows[1]["Cheese"] = "Standard Mozzarella"
    assert 1 in duplicate_issues(rows)


def test_the_same_name_with_different_serving_sizes_is_not_a_duplicate():
    from pipeline.validate import duplicate_issues
    a = {"Product_Name": "BBQ Dip", "Category": "Dips", "Serving_Size": "100", "region": "UK", "energykCal_Per Portion": "1"}
    assert duplicate_issues([a, a | {"Serving_Size": "25", "energykCal_Per Portion": "2"}]) == {}


def test_rows_that_differ_only_in_their_notes_are_not_conflicting_duplicates():
    add_on = {"Product_Name": "smoked streaky bacon", "Category": "BURGERS", "energykCal_Per Portion": "104"}
    assert duplicate_issues([add_on | {"notes": "Add-on to A"}, add_on | {"notes": "Add-on to B"}]) == {}
    assert list(duplicate_issues([add_on, add_on | {"energykCal_Per Portion": "105"}])) == [1]

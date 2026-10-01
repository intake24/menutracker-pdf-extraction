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

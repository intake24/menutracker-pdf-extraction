import pytest

from pipeline.allergens import UnknownAllergen
from pipeline.ingest import Word
from pipeline.parsers.allergen_matrix import parse_pages

LABELS = {"Egg": "egg", "Milk": "milk", "Almond": "treeNuts", "Hazelnut": "treeNuts"}
MARKERS = {"✓": "Yes", "▲": "May contain", "": ""}
KW = dict(labels=LABELS, markers=MARKERS, sizes=["Large", "Small"], units=["g", "ml"], group_column_end=90,
          variants=["Hazelnut", "Soya Milk"])
COLS = {"Egg": 400, "Milk": 430, "Almond": 460, "Hazelnut": 490}   # label x0; each label is 9 pt wide


def w(text, x, y, width=None):
    return Word(x, y, x + (width or 6 * len(text)), y + 10, text)


def header():
    return [Word(x, 20, x + 9, 50, label) for label, x in COLS.items()]


def row(y, name, size, amount, kcal, marks=(), name_x=120):
    ws = [w(name, name_x, y)] if name else []
    if size:
        ws.append(w(size, 200, y))
    ws += [w(amount, 250, y), w("ml", 275, y), w(kcal, 320, y)]
    ws += [w(m, COLS[label] + 1, y, 6) for label, m in marks]
    return ws


def parse(*lines):
    return parse_pages([header() + [x for line in lines for x in line]], **KW)


def test_a_mark_is_matched_to_its_column_by_position_and_gluten_style_groups_merge_nuts():
    rows = parse(row(100, "Pepsi", "", "330", "139", [("Milk", "✓"), ("Hazelnut", "▲")]))
    r = rows[0]
    assert (r["Product_Name"], r["Serving_Size"], r["Serving_Size_Unit"], r["energykCal_Per Portion"]) == ("Pepsi", "330", "ml", "139")
    assert (r["milk"], r["egg"], r["treeNuts"], r["treeNutSource"]) == ("Yes", "", "May contain", "Hazelnut (May contain)")


def test_marks_beside_a_size_group_cover_every_size_and_the_name_is_shared():
    rows = parse(row(100, "", "Large", "900", "300"), [w("Cola", 40, 114)] + row(114, "", "Small", "500", "150", [("Egg", "✓")]),
                 row(128, "", "Small", "250", "80"))
    assert [(r["Product_Name"], r["Size"]) for r in rows] == [("Cola", "Large"), ("Cola", "Small"), ("Cola", "Small")]
    assert {r["egg"] for r in rows} == {"Yes"}


def test_a_per_100g_row_keeps_its_basis_and_has_no_serving_size():
    line = [w("Whipped Cream", 120, 100), w("Per", 220, 100), w("100g", 235, 100), w("336", 320, 100)]
    r = parse(line)[0]
    assert r["energykCal_Per 100g/ml"] == "336" and "Serving_Size" not in r and "energykCal_Per Portion" not in r


def test_an_item_with_no_amount_or_calories_is_still_a_row():
    r = parse([w("Draught Lager", 150, 100)] + [w("✓", 401, 100, 6)])[0]
    assert r["Product_Name"] == "Draught Lager" and r["egg"] == "Yes" and "energykCal_Per Portion" not in r


def test_unknown_marker_label_and_stray_mark_raise():
    with pytest.raises(UnknownAllergen):
        parse(row(100, "Pepsi", "", "330", "139", [("Milk", "X")]))
    with pytest.raises(ValueError, match="under no allergen column"):
        parse(row(100, "Pepsi", "", "330", "139") + [w("✓", 520, 100, 6)])
    with pytest.raises(ValueError, match="unknown header word"):
        parse_pages([header() + [Word(500, 30, 509, 50, "Pecan")] + row(100, "Pepsi", "", "330", "139")], **KW)


def test_an_unreadable_data_row_raises():
    with pytest.raises(ValueError, match="cannot read a data row"):
        parse([w("Pepsi", 120, 100), w("330", 250, 100), w("litres", 275, 100)])


def test_variant_rows_keep_their_own_marks():
    rows = parse(row(100, "", "Hazelnut", "15", "50", [("Egg", "✓")]), [w("Syrups", 40, 114)] + row(114, "", "Soya Milk", "15", "40", [("Milk", "✓")]))
    assert [(r["Product_Name"], r["Size"], r["egg"], r["milk"]) for r in rows] == [
        ("Syrups", "Hazelnut", "Yes", ""), ("Syrups", "Soya Milk", "", "Yes")]


def test_marks_between_two_rows_cover_both_rows():
    rows = parse(row(100, "Churros - Medium", "", "180", "715"), row(114, "Churros - Large", "", "270", "1072"),
                 [w("✓", COLS["Egg"] + 1, 106, 6)])
    assert [r["egg"] for r in rows] == ["Yes", "Yes"]


def test_marks_far_from_any_row_raise():
    with pytest.raises(ValueError, match="not beside any row"):
        parse(row(100, "Churros", "", "180", "715"), [w("✓", COLS["Egg"] + 1, 160, 6)])


def test_headings_may_contain_symbols_and_a_starred_note():
    line1 = [w("HOTDOGS", 100, 60), w("&", 160, 60), w("TOPPINGS", 175, 60)]
    line2 = [w("HOT", 100, 160), w("FOOD", 130, 160), w("*All", 330, 160), w("weights", 360, 160)]
    rows = parse(line1, row(100, "Chips", "", "165", "196"), line2, row(200, "Pizza", "", "100", "300"))
    assert [(r["Product_Name"], r["Category"]) for r in rows] == [("Chips", "HOTDOGS & TOPPINGS"), ("Pizza", "HOT FOOD")]


def test_marks_on_a_note_line_raise_instead_of_being_skipped():
    with pytest.raises(ValueError, match="marks on a note line"):
        parse([w("Note", 400, 100), w("✓", COLS["Milk"] + 1, 100, 6)])

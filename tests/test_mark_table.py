import pytest

from pipeline.parsers.mark_table import parse_page

SOURCE = {"labels": {"Vegetarians": "Suitable_for_Vegetarian", "Vegans": "Suitable_for_Vegan", "Wheat": "wheat", "Barley": "barley",
                     "Milk": "milk", "Fish": ["fish", "crustacean"]},
          "markers": {"●": "Yes", "○": "May contain"}}
COLS = {"Vegetarians": 200, "Vegans": 230, "Wheat": 280, "Barley": 300, "Milk": 340, "Fish": 380}


def w(text, x, top, upright=True, width=10):
    return {"text": text, "x0": x - width / 2, "x1": x + width / 2, "top": top, "bottom": top + 6, "upright": upright}


def header():
    """Rotated labels: each word reversed, as the PDF text layer returns them, stacked in a column."""
    out = []
    for label, x in COLS.items():
        for k, word in enumerate(label.split()):
            out.append(w(word[::-1], x + k * 4, 130, upright=False, width=5))
    return out


def row(top, name, *cells):
    out = [w(name, 100, top, width=60)] + [w(text, COLS[col], top) for col, text in cells]
    return out


def test_diet_cells_marks_and_a_section_heading_become_rows():
    words = header() + [w("Sides", 300, 180)] + row(200, "Fries", ("Vegetarians", "Yes"), ("Vegans", "No"), ("Wheat", "●"), ("Milk", "○")) \
        + row(220, "Onion", ("Vegetarians", "Yes"), ("Vegans", "Yes"), ("Barley", "○"))
    rows = parse_page(words, SOURCE, 2)
    assert [(r["Product_Name"], r["Category"]) for r in rows] == [("Fries", "Sides"), ("Onion", "Sides")]
    assert (rows[0]["Suitable_for_Vegetarian"], rows[0]["Suitable_for_Vegan"], rows[0]["wheat"], rows[0]["milk"]) == ("Yes", "No", "Yes", "May contain")
    assert "barley" not in rows[0] and rows[1]["barley"] == "May contain" and rows[0]["source_page"] == 2


def test_a_label_can_set_several_columns_and_a_wrapped_name_joins_its_row():
    words = header() + row(200, "Mozzarella Sticks", ("Vegetarians", "Yes"), ("Vegans", "No"), ("Fish", "●")) + [w("for dips", 100, 207, width=40)]
    rows = parse_page(words, SOURCE, 2)
    assert rows[0]["Product_Name"] == "Mozzarella Sticks for dips" and rows[0]["fish"] == "Yes" and rows[0]["crustacean"] == "Yes"


def test_a_note_in_a_cell_is_kept_in_notes():
    words = header() + row(200, "Burger", ("Vegetarians", "No"), ("Vegans", "No"), ("Barley", "●")) + [w("<20ppm", 300, 207)]
    rows = parse_page(words, SOURCE, 2)
    assert rows[0]["barley"] == "Yes" and rows[0]["notes"] == "Barley <20ppm"


def test_unknown_labels_marks_diet_words_and_missing_headers_raise():
    with pytest.raises(ValueError, match="Mystery"):
        parse_page(header() + [w("yretsyM", 420, 130, upright=False, width=5)] + row(200, "A", ("Vegetarians", "Yes")), SOURCE, 2)
    with pytest.raises(ValueError, match="▲"):
        parse_page(header() + row(200, "A", ("Vegetarians", "Yes"), ("Wheat", "▲")), SOURCE, 2)
    with pytest.raises(ValueError, match="Maybe"):
        parse_page(header() + row(200, "A", ("Vegetarians", "Maybe")), SOURCE, 2)
    with pytest.raises(ValueError, match="header"):
        parse_page(row(200, "A", ("Vegetarians", "Yes")), SOURCE, 2)


def test_a_mark_with_no_row_stops_the_run():
    with pytest.raises(ValueError, match="no row"):
        parse_page(header() + row(200, "A", ("Vegetarians", "Yes")) + [w("●", 280, 260)], SOURCE, 2)


def test_headings_in_a_row_make_one_category_and_a_new_heading_after_rows_replaces_it():
    words = header() + [w("Drinks", 300, 180)] + [w("Soft Drinks", 300, 192)] + row(210, "Cola", ("Vegetarians", "Yes"), ("Vegans", "No")) \
        + [w("Hot Drinks", 300, 232)] + row(250, "Tea", ("Vegetarians", "Yes"), ("Vegans", "Yes"))
    rows = parse_page(words, SOURCE, 2)
    assert [(r["Product_Name"], r["Category"]) for r in rows] == [("Cola", "Drinks - Soft Drinks"), ("Tea", "Hot Drinks")]


def test_text_printed_on_a_row_in_place_of_marks_is_kept_in_notes_and_is_not_a_heading():
    words = header() + row(200, "Cola", ("Vegetarians", "Yes"), ("Vegans", "No")) + [w("Refer directly", 330, 200, width=50), w("to the supplier", 380, 200, width=50)] \
        + row(220, "Tea", ("Vegetarians", "Yes"), ("Vegans", "Yes"))
    rows = parse_page(words, SOURCE, 2)
    assert rows[0]["notes"] == "Refer directly to the supplier" and rows[1]["Category"] == "" and "notes" not in rows[1]

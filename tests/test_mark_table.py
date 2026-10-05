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


def test_a_heading_line_that_starts_in_the_name_area_is_not_part_of_a_name():
    words = header() + [w("Pizzas", 300, 170)] + [w("Notes for", 100, 187, width=60), w("these pizzas", 300, 187, width=60)] + row(200, "Margherita", ("Vegetarians", "Yes"), ("Vegans", "No"))
    rows = parse_page(words, SOURCE, 2)
    assert rows[0]["Product_Name"] == "Margherita" and rows[0]["Category"] == "Pizzas - Notes for these pizzas"


def test_only_a_note_that_starts_with_less_than_is_a_note_and_a_note_between_columns_raises():
    words = header() + row(200, "Cola", ("Vegetarians", "Yes"), ("Vegans", "No")) + [w("7UP", 300, 200), w("www.7up.co.uk", 380, 200, width=70)]
    rows = parse_page(words, SOURCE, 2)
    assert rows[0]["notes"] == "7UP www.7up.co.uk" and "barley" not in rows[0]
    with pytest.raises(ValueError, match="between columns"):
        parse_page(header() + row(200, "Cola", ("Vegetarians", "Yes")) + [w("<20ppm<20ppm", 290, 207, width=36)], SOURCE, 2)


def test_page_4_of_the_pizza_hut_booklet_keeps_small_text_apart():
    from pathlib import Path

    import yaml
    from pipeline.parsers import mark_table
    root = Path(__file__).resolve().parent.parent
    source = next(s for s in yaml.safe_load((root / "config" / "chains.yaml").read_text())["8_Pizzahut"]["sources"] if s["parser"] == "mark_table")
    rows = {r["Product_Name"]: r for r in mark_table.parse(root / "inputs" / "Pizza_Hut_Restaurants_Dietary_Information_Booklet_March_2025.pdf", {**source, "pages": [4]}) if r["Category"].startswith(("Pizza Combinations", "Melts"))}
    assert "BBQ Chicken Melt (served with BBQ sauce)" in rows and rows["BBQ Chicken Melt (served with BBQ sauce)"]["notes"] == "Barley <20ppm"
    assert rows["BBQ Americano"]["notes"] == "Wheat <20ppm; Barley <20ppm" and not any("Allergen Information" in n for n in rows)

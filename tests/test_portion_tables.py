import pytest

from pipeline.ingest import Word
from pipeline.parsers.portion_tables import parse_pages

PIZZA = ["Total_Weight", "Total_Slices", "energykCal_Per Slice", "protein_Per Slice"]
PORTION = ["Serving_Size", "energykCal_Per Portion", "protein_Per Portion"]
SOURCE = {"header_words": ["Weight", "Slices", "Energy", "Protein", "per", "of", "Pizza", "(g)", "Slice", "(kcal)", "Portion", "Average"],
          "furniture": ["NUTRITIONAL INFORMATION", "*Nutritionals"],
          "shapes": {4: {"columns": PIZZA, "title": "product", "category": "Pizza"},
                     3: {"columns": PORTION, "title": "section", "extra": {"Serving_Size_Unit": "g"}}}}


def text(y, s, x0=100):
    return [Word(x0, y, x0 + 6 * len(s), y + 8, s.split()[0])] + [Word(x0 + 7 * (i + 1) * 6, y, x0 + 7 * (i + 1) * 6 + 5, y + 8, w) for i, w in enumerate(s.split()[1:])]


def row(y, name, *cells):
    words = [Word(5 + 7 * 6 * i, y, 5 + 7 * 6 * i + 5, y + 8, w) for i, w in enumerate(name.split())]
    return words + [Word(300 + 40 * i, y, 330 + 40 * i, y + 8, c) for i, c in enumerate(cells)]


def page(*items):
    out, y = [], 0
    for kind, *args in items:
        y += 14
        out += (text(y, args[0]) if kind == "t" else row(y, *args))
    return out


HEADER = ("t", "Weight of Pizza (g)"), ("t", "Energy per Slice (kcal)")


def test_a_title_above_size_rows_is_the_product_and_the_row_is_its_size():
    rows = parse_pages([page(*HEADER, ("t", "Veggie Supreme"), ("r", "Individual Pan", "493", "6", "162", "6.2"),
                             ("r", "Sharing Pan", "1011", "8", "241", "9"))], SOURCE, [1])
    assert [(r["Product_Name"], r["Size"], r["Category"]) for r in rows] == [("Veggie Supreme", "Individual Pan", "Pizza")] * 1 + [("Veggie Supreme", "Sharing Pan", "Pizza")]
    assert (rows[0]["Total_Weight"], rows[0]["Total_Slices"], rows[0]["energykCal_Per Slice"], rows[0]["source_page"]) == ("493", "6", "162", 1)


def test_text_before_another_title_is_a_section_heading_and_it_persists():
    rows = parse_pages([page(*HEADER, ("t", "Buffet Pizzas"), ("t", "Margherita"), ("r", "Individual Pan", "398", "6", "169", "7.0"),
                             ("t", "Pepperoni"), ("r", "Individual Pan", "400", "6", "181", "7.2"))], SOURCE, [1])
    assert [(r["Product_Name"], r["Category"]) for r in rows] == [("Margherita", "Buffet Pizzas"), ("Pepperoni", "Buffet Pizzas")]


def test_in_a_section_shape_the_title_is_the_category_and_rows_are_products():
    rows = parse_pages([page(("t", "Average Portion (g) Energy Protein"), ("t", "Flatbreads"), ("r", "Chicken Delight Flatbread", "289", "499", "27"),
                             ("r", "Little Goat Flatbread", "295", "492", "24"), ("t", "Melts"), ("r", "Pepperoni Melt", "277", "749", "31"))], SOURCE, [1])
    assert [(r["Product_Name"], r["Category"], r["Serving_Size"], r["Serving_Size_Unit"]) for r in rows] == [
        ("Chicken Delight Flatbread", "Flatbreads", "289", "g"), ("Little Goat Flatbread", "Flatbreads", "295", "g"), ("Pepperoni Melt", "Melts", "277", "g")]
    assert "Size" not in rows[0]


def test_furniture_lines_are_skipped_and_the_category_carries_to_the_next_page():
    p1 = page(*HEADER, ("t", "Vegan Pizzas"), ("t", "Vegan Margherita"), ("r", "Individual Pan", "398", "6", "169", "7.0"))
    p2 = page(("t", "NUTRITIONAL INFORMATION (updated March 2025)"), *HEADER, ("t", "Vegan Veggie"), ("r", "Sharing Pan", "900", "8", "200", "9"), ("t", "*Nutritionals do not include salad"))
    rows = parse_pages([p1, p2], SOURCE, [1, 2])
    assert [(r["Product_Name"], r["Category"], r["source_page"]) for r in rows] == [("Vegan Margherita", "Vegan Pizzas", 1), ("Vegan Veggie", "Vegan Pizzas", 2)]


def test_a_size_row_with_no_title_a_line_with_the_wrong_number_of_cells_and_unlisted_pages_are_handled():
    with pytest.raises(ValueError, match="no product title"):
        parse_pages([page(*HEADER, ("r", "Individual Pan", "493", "6", "162", "6.2"))], SOURCE, [1])
    with pytest.raises(ValueError, match="5 numbers"):
        parse_pages([page(*HEADER, ("t", "Veggie"), ("r", "Individual Pan", "493", "6", "162", "6.2", "1"))], SOURCE, [1])
    assert parse_pages([page(*HEADER, ("t", "Veggie"), ("r", "Individual Pan", "493", "6", "162", "6.2")), page(("t", "Whatever"))], SOURCE, [1]) != []



def test_a_run_of_headings_is_one_category_joined_with_a_dash():
    rows = parse_pages([page(("t", "Average Portion (g) Energy Protein"), ("t", "Buffet Sides"), ("t", "Buffet Pasta"), ("r", "Tomato Pasta", "82", "100", "2.3"))], SOURCE, [1])
    assert rows[0]["Category"] == "Buffet Sides - Buffet Pasta"

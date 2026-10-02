from pathlib import Path

import pytest

from pipeline.ingest import Word
from pipeline.parsers.numeric_table import parse, parse_pages

PDF = Path(__file__).resolve().parent.parent / "inputs" / "nutrition.pdf"
COLUMNS = ["energykJ_Per Portion", "energykCal_Per Portion", "fat_Per Portion",
           "energykJ_Per 100g/ml", "energykCal_Per 100g/ml", "fat_Per 100g/ml"]
RIGHT_EDGES = [200, 240, 280, 340, 380, 420]   # right edge (pt) of each column


def line(y: float, name: str, cells: dict[int, str], x0: float = 5) -> list[Word]:
    """A synthetic table line: a name at x0 and cells keyed by column index, right-aligned on the column edge."""
    words = [Word(x0, y, x0 + 6 * len(name), y + 8, name)]
    for i, text in cells.items():
        words.append(Word(RIGHT_EDGES[i] - 5 * len(text), y, RIGHT_EDGES[i], y + 8, text))
    return words


FULL = {0: "323", 1: "78", 2: "5.5", 3: "2306", 4: "554", 5: "39"}


@pytest.fixture(scope="module")
def five_guys():
    cols = ["energykJ_Per Portion", "energykCal_Per Portion", "fat_Per Portion", "saturates_Per Portion",
            "carbohydrates_Per Portion", "sugars_Per Portion", "fibre_Per Portion", "protein_Per Portion",
            "salt_Per Portion"]
    return parse(PDF, {"columns": cols + [c.replace("Per Portion", "Per 100g/ml") for c in cols]})


def test_five_guys_every_item_with_its_section(five_guys):
    assert len(five_guys) == 54
    assert [r["Category"] for r in five_guys[:2]] == ["MEAT", "MEAT"]
    assert {r["Category"] for r in five_guys} == {"MEAT", "BUN", "FRIES", "TOPPINGS", "MILKSHAKES (MIX-INS)",
                                                  "LITTLE MILKSHAKES (MIX-INS)", "OTHER ITEMS"}


def test_five_guys_values_as_printed_in_their_columns(five_guys):
    bacon = five_guys[0]
    assert bacon["Product_Name"] == "Bacon" and bacon["source_page"] == 1
    assert (bacon["energykJ_Per Portion"], bacon["energykCal_Per Portion"], bacon["salt_Per Portion"]) == ("323", "78", "0.92")
    assert (bacon["energykJ_Per 100g/ml"], bacon["salt_Per 100g/ml"]) == ("2306", "6.6")
    assert next(r for r in five_guys if r["Product_Name"] == "Reg Fries - Cooked in peanut oil")["fat_Per Portion"] == "63"


def test_blank_cells_stay_in_their_columns(five_guys):
    peanuts = next(r for r in five_guys if r["Product_Name"] == "Bulk Peanuts Without Shell")
    assert "energykJ_Per Portion" not in peanuts and peanuts["energykJ_Per 100g/ml"] == "2462"


def test_blank_leading_cell_on_a_synthetic_row():
    page = line(100, "Salad", FULL) + line(110, "Water", {3: "0", 4: "0", 5: "0"})
    salad, water = parse_pages([page], COLUMNS)
    assert salad["energykJ_Per Portion"] == "323" and water["energykJ_Per 100g/ml"] == "0"
    assert "energykJ_Per Portion" not in water and "fat_Per Portion" not in water


def test_number_at_the_end_of_a_name_stays_in_the_name():
    page = line(100, "Beer", FULL) + [Word(5, 110, 75, 118, "Peroni"), Word(80, 110, 100, 118, "0.0")] \
        + [w for w in line(110, "", FULL) if w.text]
    beer, peroni = parse_pages([page], COLUMNS)
    assert peroni["Product_Name"] == "Peroni 0.0" and peroni["energykJ_Per Portion"] == "323"


def test_trace_words_and_less_than_values_kept_as_printed():
    page = line(100, "Sachet", {0: "16", 1: "4", 2: "Trace", 3: "<0.1", 4: "Negligible", 5: "0.0"})
    [row] = parse_pages([page], COLUMNS)
    assert (row["fat_Per Portion"], row["energykJ_Per 100g/ml"], row["energykCal_Per 100g/ml"]) == ("Trace", "<0.1", "Negligible")


def test_without_headers_a_table_ending_elsewhere_is_read_with_its_own_columns():
    def shifted(y, name, dx):
        return [w._replace(x0=w.x0 + dx, x1=w.x1 + dx) if w.text != name else w for w in line(y, name, FULL)]

    page = line(100, "Salad", FULL) + shifted(120, "Other", 60) + shifted(130, "Other2", 60)
    salad, other, other2 = parse_pages([page], COLUMNS)
    assert salad["energykJ_Per Portion"] == other["energykJ_Per Portion"] == "323"
    assert other2["fat_Per 100g/ml"] == "39"


def test_column_count_mismatch_with_config_raises():
    with pytest.raises(ValueError, match="found 6 numeric columns, config names 5"):
        parse_pages([line(100, "Salad", FULL)], COLUMNS[:5])


def test_caps_text_followed_by_other_words_is_not_a_section():
    junk = line(90, "NUTRITION", {}) + [Word(80, 90, 100, 98, "fat,")]       # table header cell, not a heading
    footer = line(95, "FGJV", {}) + [Word(40, 95, 90, 103, "©2025")]
    [row] = parse_pages([junk + footer + line(110, "Bacon", FULL)], COLUMNS)
    assert row["Category"] == ""


def test_indented_caps_line_is_not_a_section():
    [row] = parse_pages([line(90, "FOOD SAFETY FEEDBACK", {}, x0=180) + line(110, "Bacon", FULL)], COLUMNS)
    assert row["Category"] == ""


def test_heading_with_a_trailing_note_keeps_only_the_heading():
    note = [Word(70, 120, 76, 128, "-"), Word(80, 120, 120, 128, "amount")]
    bacon, shake = parse_pages([line(100, "MEAT", {}) + line(110, "Bacon", FULL)
                                + line(120, "MILKSHAKES", {}) + note + line(130, "Shake", FULL)], COLUMNS)
    assert bacon["Category"] == "MEAT" and shake["Category"] == "MILKSHAKES"


def test_a_minority_width_second_table_raises_instead_of_snapping_to_the_nearest_column():
    other = [Word(5, 140, 35, 148, "Coffee")] + [Word(x - 25, 140, x, 148, v) for x, v in
                                                  zip((225, 315, 410), ("12", "50", "3.1"))]
    page = line(100, "A", FULL) + line(110, "B", FULL) + line(120, "C", FULL) + other
    with pytest.raises(ValueError, match="Coffee.*no column"):
        parse_pages([page], COLUMNS)


def test_two_cells_in_one_column_raise():
    page = line(100, "A", FULL) + line(110, "B", FULL) + line(120, "C", FULL) + line(130, "Tea", {2: "9", 3: "5", 5: "4"}) \
        + [Word(269, 130, 274, 138, "7")]
    with pytest.raises(ValueError, match="two cells.*Tea"):
        parse_pages([page], COLUMNS)


@pytest.mark.parametrize("cell", ["-", "N/A", "0.", ".5", "1,234", "93*", "tr", "<0.5g"])
def test_a_cell_that_is_not_a_known_value_raises_instead_of_leaking_into_the_name(cell):
    page = line(100, "A", FULL) + line(110, "Odd", FULL | {1: cell})
    with pytest.raises(ValueError, match="unreadable cell"):
        parse_pages([page], COLUMNS)


def test_a_less_than_sign_extracted_as_its_own_word_raises():
    odd = line(110, "Odd", {k: v for k, v in FULL.items() if k != 5}) + [Word(392, 110, 397, 118, "<"), Word(400, 110, 420, 118, "0.1")]
    with pytest.raises(ValueError, match="unreadable cell"):
        parse_pages([line(100, "A", FULL) + odd], COLUMNS)


def test_a_footnote_marker_on_the_last_cell_does_not_make_the_row_vanish():
    page = line(100, "A", FULL) + line(110, "Odd", FULL | {5: "39*"})
    with pytest.raises(ValueError, match="unreadable cell"):
        parse_pages([page], COLUMNS)


def test_numbers_without_a_name_raise():
    with pytest.raises(ValueError, match="without a name"):
        parse_pages([line(100, "A", FULL) + [w for w in line(110, "", FULL) if w.text]], COLUMNS)


def test_text_between_rows_that_is_not_a_heading_or_note_raises():
    page = (line(100, "MEAT", {}) + line(110, "Bacon", FULL) + line(120, "Double Bacon", {})
            + line(130, "Cheeseburger", FULL) + line(140, "Beef", FULL))
    with pytest.raises(ValueError, match="between rows.*Double Bacon"):
        parse_pages([page], COLUMNS)
    page = line(100, "MEAT", {}) + line(110, "Cheeseburger", FULL) + line(120, "Drinks", {}) + line(130, "Bacon", FULL)
    with pytest.raises(ValueError, match="between rows.*Drinks"):
        parse_pages([page], COLUMNS)


def test_a_note_between_rows_is_not_an_error():
    note = [Word(70, 115, 76, 123, "-"), Word(80, 115, 120, 123, "amount")]
    rows = parse_pages([line(100, "MEAT", {}) + line(110, "Bacon", FULL) + note + line(130, "Beef", FULL)], COLUMNS)
    assert [r["Product_Name"] for r in rows] == ["Bacon", "Beef"]


# --- header blocks, per-table columns, parent titles, wrapped names ---------------------------------------

def header(y: float, section: str = "") -> list[Word]:
    """A column-header block: the section name on the left, then header words over the first column."""
    words = [Word(5, y, 5 + 6 * len(section), y + 12, w) for w in section.split()] if section else []
    return words + [Word(176, y, 200, y + 8, "Energy"), Word(206, y + 10, 240, y + 18, "(kcal)")]


def test_section_comes_from_the_header_block_and_column_header_text_is_left_out():
    page = header(10, "Starters") + line(40, "Dough Balls", FULL) + header(70, "Sides") + line(100, "Fries", FULL)
    a, b = parse_pages([page], COLUMNS, header="Energy")
    assert (a["Category"], b["Category"]) == ("Starters", "Sides")


def test_tables_on_one_page_that_share_the_last_column_each_use_their_own_columns():
    left_shifted = {i: v for i, v in FULL.items()}
    wide = [Word(RIGHT_EDGES[i] - 5 * len(v) - (40 if i < 3 else 0), 100, RIGHT_EDGES[i] - (40 if i < 3 else 0), 108, v)
            for i, v in left_shifted.items()]
    page = header(10, "Starters") + line(40, "A", FULL) + header(70, "Pasta") + [Word(5, 100, 25, 108, "B")] + wide
    a, b = parse_pages([page], COLUMNS, header="Energy")
    assert a["energykJ_Per Portion"] == b["energykJ_Per Portion"] == "323" and b["fat_Per 100g/ml"] == "39"


def test_a_table_continuing_on_the_next_page_without_a_section_name_keeps_the_section():
    p1 = header(10, "Starters") + line(40, "A", FULL)
    p2 = header(10) + line(40, "B", FULL)
    assert [r["Category"] for r in parse_pages([p1, p2], COLUMNS, header="Energy")] == ["Starters", "Starters"]


def test_a_page_title_becomes_a_persistent_parent_but_one_with_digits_does_not():
    title = [Word(5, 1, 120, 9, "Breakfast"), Word(125, 1, 150, 9, "only")]
    per100 = [Word(5, 14, 40, 22, "PER"), Word(45, 14, 90, 22, "100g")]
    p1 = title + per100 + header(30, "Eggs") + line(60, "A", FULL)
    p2 = per100 + header(30, "Drinks") + line(60, "B", FULL)
    a, b = parse_pages([p1, p2], COLUMNS, header="Energy", titles=["Breakfast only"])
    assert a["Category"] == "Breakfast only - Eggs" and b["Category"] == "Breakfast only - Drinks"


def test_wrapped_name_is_joined_when_enabled_and_raises_otherwise():
    page = (header(10, "Starters") + line(40, "A", FULL) + line(64, "Goats Cheese with dough", {})
            + line(76, "sticks", FULL) + line(100, "B", FULL))
    first, joined, last = parse_pages([page], COLUMNS, header="Energy", wrapped_names=True)
    assert joined["Product_Name"] == "Goats Cheese with dough sticks" and last["Product_Name"] == "B"
    with pytest.raises(ValueError, match="text between rows.*Goats Cheese"):
        parse_pages([page], COLUMNS, header="Energy")


def test_a_name_only_line_too_far_above_a_row_is_not_a_wrapped_name():
    page = header(10, "S") + line(40, "A", FULL) + line(60, "Orphan text", {}) + line(100, "B", FULL)
    with pytest.raises(ValueError, match="too far away"):
        parse_pages([page], COLUMNS, header="Energy", wrapped_names=True)


# --- the real Pizza Express PDFs --------------------------------------------------------------------------

PEX_COLUMNS = ["energykCal_Per Portion", "energykJ_Per Portion", "fat_Per Portion", "saturates_Per Portion",
               "carbohydrates_Per Portion", "sugars_Per Portion", "fibre_Per Portion", "protein_Per Portion",
               "salt_Per Portion"]
PEX_COLUMNS = PEX_COLUMNS + [c.replace("Per Portion", "Per 100g/ml") for c in PEX_COLUMNS]
PEX_SOURCE = {"columns": PEX_COLUMNS, "header": "Energy", "wrapped_names": True,
              "titles": ["Breakfast (selected restaurants only)"]}


@pytest.fixture(scope="module")
def pex():
    return parse(PDF.parent / "PEX-Nutritional-Menu---May-2025.ashx.pdf", PEX_SOURCE)


def test_pizza_express_every_item_with_its_section(pex):
    assert len(pex) == 453
    first = pex[0]
    assert (first["Product_Name"], first["Category"]) == ("Dough Balls - no dip", "Starters – Dough Balls")
    assert (first["energykCal_Per Portion"], first["energykJ_Per 100g/ml"], first["salt_Per 100g/ml"]) == ("245", "1248", "1.66")


def test_pizza_express_cells_printed_touching_are_split(pex):
    row = next(r for r in pex if r["Product_Name"].endswith("houmous - no salad (Dine Out)") and "Gluten" not in r["Product_Name"])
    assert (row["energykCal_Per 100g/ml"], row["energykJ_Per 100g/ml"], row["fat_Per 100g/ml"]) == ("294", "1232", "11.1")


def test_pizza_express_wrapped_names_and_the_parent_title(pex):
    names = {r["Product_Name"] for r in pex}
    assert "Goats Cheese & Beetroot Buddha Bowl with dough sticks" in names
    eggs = next(r for r in pex if r["Product_Name"] == "Eggs Benedict")
    assert eggs["Category"] == "Breakfast (selected restaurants only) - Breakfast eggs"


def test_pizza_express_blank_cell_stays_blank(pex):
    oasis = next(r for r in pex if r["Product_Name"].startswith("Oasis Summer Fruits"))
    assert len([k for k in oasis if k.endswith("Portion") or k.endswith("100g/ml")]) == 17


def test_belfast_pdf_parses_with_the_same_layout():
    rows = parse(PDF.parent / "BEL-Nutritional-Menu---May-2025.ashx.pdf", PEX_SOURCE)
    assert len(rows) == 365 and rows[0]["Category"] == "Starters – Dough Balls"


def test_a_wrapped_name_on_the_first_row_of_a_table_is_not_swallowed_into_the_section():
    page = header(10, "Starters") + line(40, "Goats Cheese with dough", {}) + line(52, "sticks", FULL)
    [row] = parse_pages([page], COLUMNS, header="Energy", wrapped_names=True)
    assert (row["Category"], row["Product_Name"]) == ("Starters", "Goats Cheese with dough sticks")
    with pytest.raises(ValueError, match="between the column headers and the first row"):
        parse_pages([page], COLUMNS, header="Energy")


# --- silent-loss guards found in review ---------------------------------------------------------------------

def test_a_line_between_rows_with_numbers_is_not_glued_onto_the_next_name():
    stray = line(52, "Lost", FULL) + [Word(430, 52, 435, 60, "7")]   # a cell right of the last column
    with pytest.raises(ValueError, match="reaches into the columns"):
        parse_pages([header(10, "S") + line(40, "A", FULL) + stray + line(64, "B", FULL)], COLUMNS,
                    header="Energy", wrapped_names=True)
    two_numbers = line(52, "Half", {0: "12", 1: "3"})
    with pytest.raises(ValueError, match="reaches into the columns"):
        parse_pages([header(10, "S") + line(40, "A", FULL) + two_numbers + line(64, "B", FULL)], COLUMNS,
                    header="Energy", wrapped_names=True)


def test_a_product_named_like_the_header_word_is_still_a_row():
    energy_bar = [Word(5, 52, 40, 60, "Energy"), Word(45, 52, 70, 60, "Bar")] + [w for w in line(52, "", FULL) if w.text]
    last = [Word(5, 76, 40, 84, "Red"), Word(45, 76, 70, 84, "Energy")] + [w for w in line(76, "", FULL) if w.text]
    page = header(10, "Drinks") + line(40, "A", FULL) + energy_bar + line(64, "B", FULL) + last
    rows = parse_pages([page], COLUMNS, header="Energy")
    assert [(r["Product_Name"], r["Category"]) for r in rows] == [
        ("A", "Drinks"), ("Energy Bar", "Drinks"), ("B", "Drinks"), ("Red Energy", "Drinks")]


def test_a_name_that_swallowed_several_numbers_raises():
    name = [Word(5 + 25 * i, 52, 25 + 25 * i, 60, w) for i, w in enumerate(["Chick", "219", "916", "12.3"])]
    with pytest.raises(ValueError, match="name contains numbers"):
        parse_pages([line(40, "A", FULL) + name + [w for w in line(52, "", FULL) if w.text]], COLUMNS)


def test_a_name_with_one_number_is_fine():
    name = [Word(5, 52, 25, 60, "2"), Word(30, 52, 60, 60, "Fried"), Word(65, 52, 90, 60, "Eggs")]
    rows = parse_pages([line(40, "A", FULL) + name + [w for w in line(52, "", FULL) if w.text]], COLUMNS)
    assert rows[1]["Product_Name"] == "2 Fried Eggs"


def test_text_above_a_table_header_that_is_not_a_listed_title_raises():
    page = [Word(5, 1, 120, 9, "Northern"), Word(125, 1, 150, 9, "Ireland")] + header(30, "Eggs") + line(60, "A", FULL)
    with pytest.raises(ValueError, match="above the table header.*Northern Ireland"):
        parse_pages([page], COLUMNS, header="Energy")
    [row] = parse_pages([page], COLUMNS, header="Energy", titles=["Northern Ireland"])
    assert row["Category"] == "Northern Ireland - Eggs"


def test_a_text_cell_inside_the_row_is_read_by_position():
    cols = ["energykCal_Per 100g/ml", "Serves", "Portion_Type", "energykCal_Per Portion", "fat_Per Portion", "fat_Per 100g/ml"]
    rows = [line(100, "Fries", {0: "260", 1: "2", 2: "Portion", 3: "259", 4: "9.5", 5: "9.5"}),
            line(112, "Wings", {0: "206", 1: "1", 2: "Piece", 3: "65", 4: "4.3", 5: "13.7"}),
            line(124, "Dip", {0: "109", 1: "1", 2: "Portion", 3: "98", 4: "5.6", 5: "6.2"})]
    out = parse_pages([[w for r in rows for w in r]], cols, text_values=["Portion", "Piece", "Dip"])
    assert [(r["Product_Name"], r["Portion_Type"], r["Serves"], r["energykCal_Per Portion"]) for r in out] == [
        ("Fries", "Portion", "2", "259"), ("Wings", "Piece", "1", "65"), ("Dip", "Portion", "1", "98")]


def test_a_word_outside_text_values_in_a_cell_still_raises():
    cols = ["energykCal_Per 100g/ml", "Serves", "Portion_Type", "energykCal_Per Portion", "fat_Per Portion", "fat_Per 100g/ml"]
    rows = [line(100, "Fries", {0: "260", 1: "2", 2: "Portion", 3: "259", 4: "9.5", 5: "9.5"}),
            line(112, "Wings", {0: "206", 1: "1", 2: "Bucket", 3: "65", 4: "4.3", 5: "13.7"})]
    with pytest.raises(ValueError):
        parse_pages([[w for r in rows for w in r]], cols, text_values=["Portion", "Piece"])


def test_furniture_above_the_header_is_ignored_but_other_text_still_raises():
    head = [Word(5, 50, 100, 58, "Running head"), Word(RIGHT_EDGES[0] - 30, 80, RIGHT_EDGES[0], 88, "Energy")]
    rows = [w for y in (100, 112, 124) for w in line(y, "Item", FULL)]
    assert len(parse_pages([head + rows], COLUMNS, header="Energy", furniture=["Running head"])) == 3
    with pytest.raises(ValueError, match="unrecognised text above the table header"):
        parse_pages([head + rows], COLUMNS, header="Energy")


def test_name_amount_moves_a_trailing_amount_into_the_serving_size():
    rows = [line(100, "BBQ Dip 25g", FULL), line(112, "Tub 330 ml", FULL), line(124, "Chicken Kickers (4)", FULL)]
    out = parse_pages([[w for r in rows for w in r]], COLUMNS, name_amount=True)
    assert [(r["Product_Name"], r.get("Serving_Size"), r.get("Serving_Size_Unit")) for r in out] == [
        ("BBQ Dip", "25", "g"), ("Tub", "330", "ml"), ("Chicken Kickers (4)", None, None)]
    plain = parse_pages([[w for r in rows for w in r]], COLUMNS)
    assert plain[0]["Product_Name"] == "BBQ Dip 25g" and "Serving_Size" not in plain[0]


def test_name_amount_handles_a_dash_before_the_amount_oz_and_trailing_words():
    rows = [line(100, "Bacon Bits - 18g", FULL), line(112, "Lemonade - 22oz Freestyle", FULL)]
    out = parse_pages([[w for r in rows for w in r]], COLUMNS, name_amount=True)
    assert [(r["Product_Name"], r["Serving_Size"], r["Serving_Size_Unit"]) for r in out] == [
        ("Bacon Bits", "18", "g"), ("Lemonade Freestyle", "22", "oz")]


def test_a_ruler_line_of_consecutive_column_numbers_is_page_furniture():
    ruler = [Word(RIGHT_EDGES[i] - 5, 60, RIGHT_EDGES[i], 68, str(i + 4)) for i in range(6)]
    rows = [w for y in (100, 112, 124) for w in line(y, "Item", FULL)]
    assert len(parse_pages([ruler + rows], COLUMNS)) == 3


def test_free_sections_turn_distant_name_only_lines_into_the_category_and_wrapped_names_still_join():
    rows = [line(100, "Item A", FULL), [Word(5, 130, 100, 138, "Cold Drinks")], [Word(5, 150, 60, 158, "Long")],
            line(160, "name", FULL)]
    out = parse_pages([[w for r in rows for w in r]], COLUMNS, wrapped_names=True, free_sections=True)
    assert [(r["Product_Name"], r["Category"]) for r in out] == [("Item A", ""), ("Long name", "Cold Drinks")]


def test_rows_overlaid_at_the_same_position_are_separate_rows_when_words_carry_layers():
    a = [w._replace(y0=100, y1=108) for w in line(100, "Onions", FULL)]
    b = [w._replace(layer=1) for w in line(100, "Guacamole", {0: "99", 1: "20", 2: "1.5", 3: "400", 4: "95", 5: "6"})]
    rows = parse_pages([a + b + line(112, "Chips", FULL)], COLUMNS)
    assert sorted(r["Product_Name"] for r in rows) == ["Chips", "Guacamole", "Onions"]
    assert {r["Product_Name"]: r["energykJ_Per Portion"] for r in rows}["Guacamole"] == "99"


def test_odeon_page_1_overlaid_rows_are_read_in_drawing_order():
    import yaml

    from pipeline.ingest import page_words_fine
    src = yaml.safe_load((Path(__file__).resolve().parent.parent / "docs" / "odeon-uk-config-draft.yaml").read_text())["59_Odeon"]["sources"][0]
    pdf = Path(__file__).resolve().parent.parent / "inputs" / src["pdf"]
    words = page_words_fine(pdf, text_flow=True)[0]
    rows = parse_pages([words], src["columns"], src["header"], True, (), (), (), True, True, ["#N/A"])
    names = {r["Product_Name"]: r for r in rows}
    assert names["Onions"]["Serving_Size"] == "142" and names["Guacamole (New)"]["Serving_Size"] == "90"
    assert names["Onions"]["energykCal_Per Portion"] != names["Guacamole (New)"]["energykCal_Per Portion"]


def test_invalid_values_are_kept_as_printed_under_any_column_and_other_words_still_raise():
    cols = ["energykCal_Per Portion", "fat_Per Portion", "protein_Per Portion"]
    ok = [line(100, "Hidden", {0: "#N/A", 1: "#N/A", 2: "#N/A"}), line(112, "Real", {0: "5", 1: "6", 2: "7"}),
          line(124, "Other", {0: "8", 1: "9", 2: "1"})]
    out = parse_pages([[w for r in ok for w in r]], cols, invalid_values=["#N/A"])
    assert out[0]["energykCal_Per Portion"] == "#N/A"
    with pytest.raises(ValueError):
        parse_pages([[w for r in ok for w in r]], cols)

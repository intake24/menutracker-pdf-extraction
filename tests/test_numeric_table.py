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


def test_a_second_table_with_different_columns_on_the_page_raises():
    shifted = [w._replace(x0=w.x0 + 60, x1=w.x1 + 60) if w.text != "Other" else w for w in line(120, "Other", FULL)]
    with pytest.raises(ValueError, match="numeric columns"):
        parse_pages([line(100, "Salad", FULL) + shifted], COLUMNS)


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

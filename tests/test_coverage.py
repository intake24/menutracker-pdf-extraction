from pathlib import Path

from pipeline.coverage import numeric_lines, shortfalls

INPUTS = Path(__file__).resolve().parent.parent / "inputs"


def test_shortfalls_lists_pages_with_fewer_rows_than_data_looking_lines():
    rows = [{"source_page": 1}] * 3 + [{"source_page": 2}]
    assert shortfalls(rows, {1: 3, 2: 2, 3: 1}) == {2: (1, 2), 3: (0, 1)}


def test_numeric_lines_counts_lines_with_enough_numbers():
    lines = numeric_lines(INPUTS / "nutrition.pdf", 9)
    assert lines and all(n > 0 for n in lines.values()) and sum(lines.values()) >= 54

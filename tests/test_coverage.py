from pathlib import Path

from pipeline.coverage import numeric_lines, shortfalls

INPUTS = Path(__file__).resolve().parent.parent / "inputs"


def test_shortfalls_lists_pages_with_fewer_rows_than_data_looking_lines():
    rows = [{"source_page": 1}] * 3 + [{"source_page": 2}]
    assert shortfalls(rows, {1: 3, 2: 2, 3: 1}) == {2: (1, 2), 3: (0, 1)}


def test_numeric_lines_counts_lines_with_enough_numbers():
    lines = numeric_lines(INPUTS / "nutrition.pdf", 9)
    assert lines and all(n > 0 for n in lines.values()) and sum(lines.values()) >= 54


def test_page_gaps_flags_a_page_with_fewer_rows_than_the_source_usually_has_per_data_line():
    from pipeline.coverage import page_gaps
    lines = {1: 10, 2: 10, 3: 10, 4: 9}
    rows = [{"source_page": p} for p in (1, 2, 3, 4) for _ in range(10 if p != 3 else 9)]   # page 3 lost one row
    rows = [r for r in rows if not (r["source_page"] == 4)] + [{"source_page": 4}] * 9
    assert page_gaps(rows, lines) == {3: (9, 10)}


def test_page_gaps_scales_for_layouts_with_several_data_lines_per_row_and_ignores_merged_page_labels():
    from pipeline.coverage import page_gaps
    lines = {1: 45, 2: 45, 3: 45, 4: 36}               # nine figure lines per product
    rows = [{"source_page": p} for p in (1, 2, 3) for _ in range(5)] + [{"source_page": 4}] * 3      # page 4 should have 4 products
    assert page_gaps(rows, lines) == {4: (3, 4)}
    merged = [{"source_page": "17, 2"}] * 3
    assert page_gaps(merged, {2: 3, 17: 3}) == {}      # a merged row names both of its pages: counted on each

> **Historical plan.** Kept as a record of how the work was planned; the state of the project is in `docs/start-here.md` and `docs/end-of-round-report-2026-10.md`.

# Phase 2a: Generic Numeric-Table Parser + Five Guys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic parser for "item name followed by a row of numbers" nutrition tables, and use it to produce `52_FiveGuys.csv`, checked against Pearl Scan ground truth (54 rows, 972 nutrient cells).

**Architecture:**
- `numeric_table` reads word coordinates (`pdftotext -bbox`) and finds numeric columns by position: on each page the right edges of the numeric cells are clustered into columns, and the source's `columns` list in `config/chains.yaml` names them left to right.
- Because columns come from position, not token count, rows with blank cells land in the right columns.
- Section headings become `Category`.
- A small fix lets `eval` read Pearl Scan files that are Windows-1252 rather than UTF-8.
- No LLM calls.

**Tech Stack:** Python 3.12, `uv`, `pydantic` v2, `pyyaml`, `pytest`, poppler. No new dependencies.

**Spec:** [docs/pipeline-design.md](../../pipeline-design.md), draft v3. This plan implements slice 2a of §10. The Phase 2 survey findings are in §2.

## Global Constraints

- Git holds code, `schemas/`, `config/` and `golden/` only. Data (`inputs/`, `outputs/`, `samples/`, `work/`) is gitignored. Tests read PDFs and ground truth from the local `inputs/`.
- Runtime dependencies stay `pydantic>=2.9` and `pyyaml>=6`; dev dependency `pytest>=8`. Add nothing else in this phase.
- No LLM or network calls.
- **Extract, don't transform.** Cells are written exactly as printed: strings such as `"323"`, `"0.92"`, `"Trace"`, `"<0.1"`. No unit or basis conversion, nothing derived.
- Allergen cells stay `Yes` / `May contain` / `No` / blank. A PDF with no allergen information produces no allergen columns (all blank), and its source has no `markers`.
- Unknown column names stop the run (`finalise` raises). The config's `columns` must name dictionary columns.
- `run` refuses a chain with any source not marked `approved: true`. Only a person sets `approved: true`.
- Row problems are never dropped and values are never changed; every issue goes into `flags` with the prefix `error:` or `warn:`. Flags can come from the **source**: Five Guys prints figures that fail the arithmetic checks.
- Existing behaviour is unchanged: the Phase 1 chains still produce 207 rows each with no flags.

## Review Focus

1. **A row with blank cells** (Five Guys "Bulk Peanuts Without Shell" has per-100g values only). Expected: each printed value lands in its own column and the blanks stay blank, never shifted left. Tests: Task 2 `test_blank_cells_stay_in_their_columns`, `test_blank_leading_cell_on_a_synthetic_row`.
2. **A product name ending in a number** ("Peroni Nastro Azzurro 0.0"). Expected: the number stays in the name and is not read as the first nutrient. Test: Task 2 `test_number_at_the_end_of_a_name_stays_in_the_name`.
3. **A second table on the same page with different column positions** (Pizza Express page 19). Expected: a loud `ValueError` naming the page, never values assigned to merged or wrong columns. Test: Task 2 `test_a_second_table_with_different_columns_on_the_page_raises`.
4. **Header, footer and note text read as a section heading** ("NUTRITION fat, g", "FGJV ©2025", an indented "FOOD SAFETY FEEDBACK"). Expected: not a `Category`. Tests: Task 2 `test_caps_text_followed_by_other_words_is_not_a_section`, `test_indented_caps_line_is_not_a_section`.
5. **Arithmetic problems that are in the source itself** (Lettuce: 58 kJ but 19 kcal). Expected: flagged, value unchanged. Test: Task 3 `test_five_guys_flags_are_arithmetic_inconsistencies_in_the_source`.
6. **A Pearl Scan file that isn't UTF-8** (12 of the 42 are Windows-1252). Expected: read correctly, not a crash. Test: Task 1 `test_read_csv_falls_back_to_windows_1252`.

---

## File Structure

| Path | Change | Responsibility |
|---|---|---|
| `pipeline/evaluate.py` | modify | `read_csv` falls back to Windows-1252 |
| `pipeline/parsers/numeric_table.py` | create | Generic numeric-table layout parser |
| `pipeline/parsers/__init__.py` | modify | Register `numeric_table` |
| `pipeline/cli.py` | modify | A source without `markers` is allowed (cache key) |
| `config/chains.yaml` | modify | Add `52_FiveGuys`; document `columns` |
| `tests/test_evaluate.py`, `tests/test_numeric_table.py`, `tests/test_cli.py`, `tests/test_ingest.py` | create/modify | Tests |

Not in this slice: Pizza Express (slice 2b needs character-level extraction and per-table column positions), section names printed beside a column header, and any allergen columns for numeric tables.

---

### Task 1: Read Windows-1252 ground-truth files

**Files:**
- Modify: `pipeline/evaluate.py` (replace the whole file)
- Test: `tests/test_evaluate.py` (replace the whole file)

**Interfaces:**
- Consumes: nothing new.
- Produces: `pipeline.evaluate.read_csv(path: Path) -> list[dict]`, now decoding UTF-8 (with or without BOM) and falling back to Windows-1252. All other functions in `evaluate.py` are unchanged.

- [ ] **Step 1: Write the failing test**

Replace `tests/test_evaluate.py` with the following; the only new test is the last one.

`tests/test_evaluate.py`:

```python
from pipeline.evaluate import compare_golden, compare_ground_truth, ground_truth_file, same

MAPPING = {"item_name": "Product_Name", "kcal": "energykCal_Per Portion", "fat": "fat_Per Portion"}
OURS = [{"Product_Name": "Sweet Popcorn", "Size": "Large", "energykCal_Per Portion": "958.9", "fat_Per Portion": "Negligible"},
        {"Product_Name": "Croissant", "Size": "", "energykCal_Per Portion": "167", "fat_Per Portion": "7.7"}]


def test_same_compares_numbers_as_numbers_and_words_case_insensitively():
    assert same("7.70", "7.7") and same("Negligible", "negligible") and not same("7.7", "7.8")


def test_ground_truth_file_prefers_corrected_version(tmp_path):
    (tmp_path / "Odeon" / "Previous").mkdir(parents=True)
    for p in ["Odeon/menu.csv", "Odeon/menu_v0.1.csv", "Odeon/Previous/menu.csv"]:
        (tmp_path / p).write_text("item_name\n")
    assert ground_truth_file(tmp_path, "menu") == tmp_path / "Odeon" / "menu_v0.1.csv"
    assert ground_truth_file(tmp_path, "other") is None


def test_rows_match_on_name_plus_size_and_cells_compare():
    truth = [{"item_name": "Sweet Popcorn - Large", "kcal": "958.9", "fat": "Negligible"},
             {"item_name": "Croissant", "kcal": "167", "fat": "7.7"}]
    r = compare_ground_truth(truth, OURS, MAPPING, set())
    assert r["passed"] and r["recall"] == 1.0 and r["cells"] == 4


def test_mismatch_and_unmatched_fail_unless_in_errata():
    truth = [{"item_name": "Croissant", "kcal": "176", "fat": "7.7"}, {"item_name": "Ghost Bun", "kcal": "1", "fat": "1"}]
    r = compare_ground_truth(truth, OURS, MAPPING, set())
    assert not r["passed"] and r["unmatched"] == ["Ghost Bun"]
    assert r["mismatches"] == ["Croissant.kcal: Pearl Scan '176', ours '167'"]
    r = compare_ground_truth(truth, OURS, MAPPING, {("Croissant", "kcal"), ("Ghost Bun", "*")})
    assert r["passed"] and r["rows"] == 1


def test_golden_rows_must_match_exactly():
    golden = [{"Product_Name": "Croissant", "Category": "BAKERY", "milk": "Yes"}]
    ours = [{"Product_Name": "Croissant", "Category": "BAKERY", "milk": "May contain"}]
    assert compare_golden(golden, ours) == ["Croissant.milk: expected 'Yes', got 'May contain'"]
    assert compare_golden(golden, []) == ["missing row: Croissant (BAKERY)"]


def test_blank_golden_cell_matches_a_column_the_chain_csv_left_out():
    golden = [{"Product_Name": "Croissant", "Category": "BAKERY", "spelt": "", "milk": "Yes"}]
    ours = [{"Product_Name": "Croissant", "Category": "BAKERY", "milk": "Yes"}]
    assert compare_golden(golden, ours) == []
    assert compare_golden([golden[0] | {"spelt": "No"}], ours) == ["Croissant: column 'spelt' not in output"]


def test_read_csv_falls_back_to_windows_1252(tmp_path):
    from pipeline.evaluate import read_csv
    path = tmp_path / "pearl.csv"
    path.write_bytes("item_name,kcal\nJalapeño Peppers,4\n".encode("cp1252"))
    assert read_csv(path) == [{"item_name": "Jalapeño Peppers", "kcal": "4"}]
    path.write_bytes("item_name,kcal\nJalapeño Peppers,4\n".encode("utf-8-sig"))
    assert read_csv(path)[0]["item_name"] == "Jalapeño Peppers"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_evaluate.py -v` Expected: `test_read_csv_falls_back_to_windows_1252` FAILS with `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xf1`; the other 6 pass.

- [ ] **Step 3: Implement**

Replace `pipeline/evaluate.py`:

```python
"""Compare our output with Pearl Scan ground truth (nutrition) and hand-verified golden rows (allergens)."""
import csv
import io
import re
from pathlib import Path

ROW_RECALL_MIN = 0.99


def read_csv(path: Path) -> list[dict]:
    """Read a CSV as UTF-8, or as Windows-1252 when it isn't (Pearl Scan files exported from Excel)."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    return list(csv.DictReader(io.StringIO(text, newline="")))


def same(want: str, got: str) -> bool:
    try:
        return float(want) == float(got)
    except ValueError:
        return want.strip().casefold() == got.strip().casefold()


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def ground_truth_file(gt_dir: Path, pdf_stem: str) -> Path | None:
    """Newest Pearl Scan CSV for a PDF: `<stem>_v0.1.csv` beats `<stem>.csv`; `Previous/` is ignored."""
    found = [p for p in gt_dir.rglob("*.csv")
             if "Previous" not in p.parts and p.stem in (pdf_stem, f"{pdf_stem}_v0.1")]
    return max(found, key=lambda p: p.stem.endswith("_v0.1"), default=None)


def compare_ground_truth(truth: list[dict], ours: list[dict], mapping: dict[str, str],
                         errata: set[tuple[str, str]]) -> dict:
    """Match rows on name (+ size), then compare every mapped cell.

    errata: {(item_name, pearlscan_column)}; column "*" excuses a whole row.
    """
    by_key: dict[str, dict] = {}
    for r in ours:
        by_key.setdefault(norm(r["Product_Name"] + r.get("Size", "")), r)
    unmatched, mismatches, cells = [], [], 0
    for t in truth:
        name = t["item_name"]
        if (name, "*") in errata:
            continue
        o = by_key.get(norm(name))
        if o is None:
            unmatched.append(name)
            continue
        for gt_col, col in mapping.items():
            if gt_col not in t or gt_col == "item_name" or (name, gt_col) in errata:
                continue
            cells += 1
            if not same(t[gt_col], o.get(col, "")):
                mismatches.append(f"{name}.{gt_col}: Pearl Scan {t[gt_col]!r}, ours {o.get(col, '')!r}")
    checked = len(truth) - sum((t["item_name"], "*") in errata for t in truth)
    recall = (checked - len(unmatched)) / checked if checked else 1.0
    return {"rows": checked, "recall": recall, "cells": cells, "unmatched": unmatched, "mismatches": mismatches,
            "passed": recall >= ROW_RECALL_MIN and not mismatches}


def compare_golden(golden: list[dict], ours: list[dict]) -> list[str]:
    """Every golden row (matched on Product_Name + Category) must exist with identical cells."""
    by_key = {(r["Product_Name"], r["Category"]): r for r in ours}
    failures = []
    for g in golden:
        o = by_key.get((g["Product_Name"], g["Category"]))
        if o is None:
            failures.append(f"missing row: {g['Product_Name']} ({g['Category']})")
            continue
        for col, want in g.items():
            got = o.get(col, "" if want == "" else None)   # chain CSVs omit columns that are blank throughout
            if got is None:
                failures.append(f"{g['Product_Name']}: column {col!r} not in output")
            elif not same(want, got):
                failures.append(f"{g['Product_Name']}.{col}: expected {want!r}, got {got!r}")
    return failures
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_evaluate.py -v` Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/evaluate.py tests/test_evaluate.py
git commit -m "fix: read Windows-1252 ground-truth files"
```

---

### Task 2: Numeric-table parser

How it works, from the real Five Guys PDF (`nutrition.pdf`, 2 pages, 54 items):
- Each item is a line: name, then 18 numbers (9 per serving, 9 per 100g). Some items have blank cells (peanuts: per-100g only).
- Section headings (`MEAT`, `BUN`, `FRIES`, `TOPPINGS`, `MILKSHAKES (MIX-INS)`, `OTHER ITEMS`) are ALL-CAPS lines at the left margin.
- The milkshake heading on page 1 shares its line with a note: `MILKSHAKES (MIX-INS) - amount of individual mix-ins may vary…`. Only the leading ALL-CAPS run is the heading.
- Page 2 has a heading `LITTLE MILKSHAKES (MIX-INS)` followed by a separate note line.
- Header cells (`NUTRITION fat, g`), footers (`FGJV ©2025 …`) and `FOOD SAFETY FEEDBACK` must not become headings.

**Files:**
- Create: `pipeline/parsers/numeric_table.py`, `tests/test_numeric_table.py`
- Modify: `pipeline/parsers/__init__.py` (replace the whole file)

**Interfaces:**
- Consumes: `Word` and `page_words` from `pipeline.ingest`.
- Produces:
  - `parse(pdf: Path, source: dict) -> list[dict]`, where `source["columns"]` is the list of dictionary column names left to right.
  - `parse_pages(pages: list[list[Word]], columns: list[str]) -> list[dict]`.
  - Row keys: `Product_Name`, `Category`, `source_page`, and each named column that has a printed value, as the printed string.
  - Raises `ValueError` when a page's numeric columns don't match `columns`.
  - `PARSERS["numeric_table"]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_numeric_table.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_numeric_table.py -v` Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.parsers.numeric_table'`.

- [ ] **Step 3: Implement `pipeline/parsers/numeric_table.py`**

```python
"""Generic parser for "item name followed by a row of numbers" nutrition tables (Five Guys, Pizza Express, ...).

Columns are found by position: on each page the right edges of the numeric cells are clustered into
columns, and `source["columns"]` names them left to right. Position (not token count) is what keeps a
row with blank cells, e.g. an item with per-100g values only, in the right columns.
"""
import re
from collections import Counter
from pathlib import Path

from pipeline.ingest import Word, page_words

NUMBER = re.compile(r"^(?:<\s?)?\d+(?:\.\d+)?$|^(?:Negligible|Traces?|Tr)$")
MIN_NUMBERS = 3          # a line needs this many trailing numeric cells to be a data row
SECTION_INDENT = 12      # section headings start at the left margin; wrapped text and notes are indented more
LINE_GAP = 3             # words whose vertical centres are this close are on one line
COLUMN_GAP = 9           # right edges further apart than this (pt) belong to different columns


def _lines(words: list[Word]) -> list[list[Word]]:
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (w.y0 + w.y1) / 2):
        centre = (w.y0 + w.y1) / 2
        if lines and centre - (lines[-1][0].y0 + lines[-1][0].y1) / 2 <= LINE_GAP:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w.x0) for line in lines]


def _split(line: list[Word]) -> tuple[list[Word], list[Word]]:
    """(name words, trailing numeric cells)."""
    cut = len(line)
    while cut > 0 and NUMBER.match(line[cut - 1].text):
        cut -= 1
    return line[:cut], line[cut:]


def _heading(line: list[Word], left: float) -> str | None:
    """Section heading text: a leading run of ALL-CAPS words at the left margin, followed by nothing or a "- note"."""
    if line[0].x0 - left >= SECTION_INDENT:
        return None
    words = []
    for w in line:
        letters = [c for c in w.text if c.isalpha()]
        if not letters or not all(c.isupper() for c in letters):
            break
        words.append(w.text)
    rest = line[len(words):]
    if not words or (rest and rest[0].text != "-") or any(c.isdigit() for w in line[:len(words)] for c in w.text):
        return None
    return " ".join(words)


def _anchors(cells: list[Word]) -> list[float]:
    edges = sorted(w.x1 for w in cells)
    clusters = [[edges[0]]]
    for x in edges[1:]:
        if x - clusters[-1][-1] > COLUMN_GAP:
            clusters.append([])
        clusters[-1].append(x)
    return [sum(c) / len(c) for c in clusters]


def parse_pages(pages: list[list[Word]], columns: list[str]) -> list[dict]:
    rows = []
    category = ""
    for page_no, words in enumerate(pages, start=1):
        lines = _lines(words)
        split = [_split(line) for line in lines]
        data = [(name, cells) for name, cells in split if name and len(cells) >= MIN_NUMBERS]
        if not data:
            continue
        # Columns come from the most common row width, so a name that ends in a number
        # ("Peroni Nastro Azzurro 0.0") or a row with blank cells can't create or hide a column.
        usual = Counter(len(cells) for _, cells in data).most_common(1)[0][0]
        anchors = _anchors([c for _, cells in data if len(cells) == usual for c in cells])
        if len(anchors) != len(columns):
            raise ValueError(f"page {page_no}: found {len(anchors)} numeric columns, config names {len(columns)}")
        left = min(name[0].x0 for name, _ in data)
        for line, (name, cells) in zip(lines, split):
            if not (name and len(cells) >= MIN_NUMBERS):
                if not cells and (heading := _heading(line, left)):
                    category = heading
                continue
            while cells and cells[0].x1 < anchors[0] - COLUMN_GAP:   # left of the first column: part of the name
                name, cells = name + cells[:1], cells[1:]
            row = {"Product_Name": " ".join(w.text for w in name), "Category": category, "source_page": page_no}
            for w in cells:
                col = columns[min(range(len(anchors)), key=lambda i: abs(anchors[i] - w.x1))]
                row[col] = w.text
            rows.append(row)
    return rows


def parse(pdf: Path, source: dict) -> list[dict]:
    return parse_pages(page_words(pdf), source["columns"])
```

Replace `pipeline/parsers/__init__.py`:

```python
from pipeline.parsers import numeric_table, premier_inn_breakfast, whitbread_drinks_grid

# parser name (as used in config/chains.yaml) -> parse(pdf_path, source_config) -> rows
PARSERS = {
    "premier_inn_breakfast": premier_inn_breakfast.parse,
    "whitbread_drinks_grid": whitbread_drinks_grid.parse,
    "numeric_table": numeric_table.parse,
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_numeric_table.py -v` Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/parsers/numeric_table.py pipeline/parsers/__init__.py tests/test_numeric_table.py
git commit -m "feat: generic numeric-table layout parser"
```

---

### Task 3: Five Guys chain, optional markers, end-to-end

**Files:**
- Modify: `config/chains.yaml` (replace the whole file), `pipeline/cli.py` (replace the whole file)
- Test: `tests/test_cli.py` (replace), `tests/test_ingest.py` (replace)

**Interfaces:**
- Consumes: `PARSERS["numeric_table"]` (Task 2) and `read_csv` (Task 1, used by `eval` through `pipeline.evaluate`).
- Produces: `52_FiveGuys` in `config/chains.yaml`; `run` accepts a source with no `markers`. Everything else in `cli.py` is unchanged.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_cli.py`:

`tests/test_cli.py`:

```python
from pathlib import Path

import pytest

from pipeline.cli import SourceNotApproved, evaluate, run

ROOT = Path(__file__).resolve().parent.parent
ROWS = {"16_Beefeater": 207, "17_Brewersfayre": 207, "21_TableTable": 207, "52_FiveGuys": 54}   # breakfast+drinks / table


def chains_file(tmp_path: Path, approved: bool) -> Path:
    text = (ROOT / "config" / "chains.yaml").read_text()
    text = text.replace("approved: false", f"approved: {str(approved).lower()}")
    text = text.replace("approved: true", f"approved: {str(approved).lower()}")
    path = tmp_path / "chains.yaml"
    path.write_text(text)
    return path


def test_run_writes_one_csv_per_chain_and_passes_eval(tmp_path):
    cf = chains_file(tmp_path, approved=True)
    written = run(ROOT / "inputs", cf, tmp_path / "out")
    assert {p.stem: len(rows) for p, rows in written.items()} == ROWS
    for path, rows in written.items():
        flagged = [r for r in rows if r["flags"]]
        if path.stem != "52_FiveGuys":
            assert not flagged
        assert {r["region"] for r in rows} == {"UK"} and {r["method"] for r in rows} == {"parser"}
    failures = evaluate(cf, tmp_path / "out", ROOT / "inputs" / "ground-truth", ROOT / "golden", ROOT / "config")
    assert failures == []


def test_chain_without_allergen_information_has_no_allergen_columns(tmp_path):
    written = run(ROOT / "inputs", chains_file(tmp_path, approved=True), tmp_path / "out", "52_FiveGuys")
    [(path, rows)] = written.items()
    header = path.read_text().splitlines()[0].split(",")
    assert "milk" not in header and "gluten" not in header
    assert "energykJ_Per 100g/ml" in header and "energykJ_Per Portion" in header
    assert {r["source_file"] for r in rows} == {"nutrition.pdf"}


def test_five_guys_flags_are_arithmetic_inconsistencies_in_the_source(tmp_path):
    """Pearl Scan agrees with every value, so these are faithful to the PDF; flagged, never changed."""
    written = run(ROOT / "inputs", chains_file(tmp_path, approved=True), tmp_path / "out", "52_FiveGuys")
    [(_, rows)] = written.items()
    flagged = {r["Product_Name"]: r["flags"] for r in rows if r["flags"]}
    assert sorted(flagged) == ["Banana", "Banana Little", "Green Peppers", "HP Brown Sauce", "Jalapeño Peppers",
                               "Lettuce", "Mango", "Peanut Butter", "Relish"]
    arithmetic = ("error: kJ/kcal", "error: saturates >", "error: sugars >", "warn: Atwater")
    assert all(f.startswith(arithmetic) for flags in flagged.values() for f in flags.split(" | "))
    lettuce = next(r for r in rows if r["Product_Name"] == "Lettuce")
    assert (lettuce["energykJ_Per 100g/ml"], lettuce["energykCal_Per 100g/ml"]) == ("58", "19")


def test_run_refuses_unapproved_sources(tmp_path):
    with pytest.raises(SourceNotApproved):
        run(ROOT / "inputs", chains_file(tmp_path, approved=False), tmp_path / "out")
```

Replace `tests/test_ingest.py`; the only change is the chains test, which now expects four chains:

`tests/test_ingest.py`:

```python
from pathlib import Path

from pipeline.ingest import load_chains, manifest_row, page_texts, page_words, sources_by_pdf, text_sha

INPUTS = Path(__file__).resolve().parent.parent / "inputs"
BREAKFAST = [
    "beefeater_ss25_breakfast_menu_allergy_nutrition_v1.pdf",
    "brewers_fayre_allergy_nutrition_ss25_breakfast_menu.pdf",
    "table_table_allergy_nutrition_ss25_breakfast_menu.pdf",
]


def test_page_texts_one_per_page():
    assert len(page_texts(INPUTS / BREAKFAST[0])) == 7


def test_page_words_have_boxes_and_unescaped_text():
    pages = page_words(INPUTS / "beefeater_ss25_drinks_menu_allergy_nutrition_v1.pdf")
    assert len(pages) == 8
    words = [w for w in pages[2] if w.text == "&"]
    assert words and all(w.x1 > w.x0 and w.y1 > w.y0 for w in words)


def test_identical_pdfs_share_text_sha():
    assert len({text_sha(page_texts(INPUTS / f)) for f in BREAKFAST}) == 1


def test_one_pdf_per_source_and_four_chains_configured():
    chains = load_chains()
    assert set(chains) == {"16_Beefeater", "17_Brewersfayre", "21_TableTable", "52_FiveGuys"}
    assert all(len(users) == 1 for users in sources_by_pdf(chains).values())


def test_image_only_pages_reported():
    row = manifest_row(INPUTS / "nutritional-information.pdf", {})
    assert row["chains"] == "" and row["parser"] == "unassigned"
    assert len(row["image_pages"].split()) == 79
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cli.py tests/test_ingest.py -v` Expected: FAIL. `test_run_writes_one_csv_per_chain_and_passes_eval`, `test_chain_without_allergen_information_has_no_allergen_columns`, `test_five_guys_flags_are_arithmetic_inconsistencies_in_the_source` and `test_one_pdf_per_source_and_four_chains_configured` fail because `52_FiveGuys` doesn't exist yet; the other tests pass.

- [ ] **Step 3: Implement**

`pipeline/cli.py` changes in one place, the cache key: `source["markers"]` becomes `source.get("markers", {})`. Replace the whole file:

```python
import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

import yaml

from pipeline.columns import load_columns
from pipeline.evaluate import compare_golden, compare_ground_truth, ground_truth_file, read_csv
from pipeline.export import finalise, write_csv
from pipeline.ingest import load_chains, manifest_row, page_texts, text_sha
from pipeline.parsers import PARSERS

ROOT = Path(__file__).resolve().parent.parent


class SourceNotApproved(Exception):
    pass


def manifest(inputs: Path, chains_file: Path, out: Path) -> list[dict]:
    chains = load_chains(chains_file)
    rows = [manifest_row(p, chains) for p in sorted(inputs.glob("*.pdf"))]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return rows


def run(inputs: Path, chains_file: Path, outputs: Path, only: str | None = None) -> dict[Path, list[dict]]:
    """Write outputs/<chain key>.csv for every chain whose sources are all approved.

    PDFs with identical text and the same parser and markers are parsed once.
    """
    chains = load_chains(chains_file)
    columns = load_columns()
    parsed: dict[tuple, list[dict]] = {}
    written: dict[Path, list[dict]] = {}
    for key, chain in chains.items():
        if only and key != only:
            continue
        rows: list[dict] = []
        for source in chain["sources"]:
            if not source.get("approved"):
                raise SourceNotApproved(f"{key}: {source['pdf']} is not approved in {chains_file.name}")
            pdf = inputs / source["pdf"]
            cache_key = (text_sha(page_texts(pdf)), source["parser"], repr(sorted(source.get("markers", {}).items())))
            if cache_key not in parsed:
                parsed[cache_key] = PARSERS[source["parser"]](pdf, source)
            rows += [r | {"region": source["region"], "source_file": pdf.name, "method": "parser"}
                     for r in parsed[cache_key]]
        rows = finalise(rows, columns)
        path = outputs / f"{key}.csv"
        write_csv(rows, columns, path)
        written[path] = rows
    return written


def evaluate(chains_file: Path, outputs: Path, ground_truth: Path, golden: Path, config: Path) -> list[str]:
    """Nutrition vs Pearl Scan ground truth, allergens vs hand-verified golden rows. Returns failure lines."""
    mapping = yaml.safe_load((config / "pearlscan_columns.yaml").read_text())
    errata_rows = yaml.safe_load((config / "ground_truth_errata.yaml").read_text()) or []
    failures = []
    for key, chain in load_chains(chains_file).items():
        out = outputs / f"{key}.csv"
        if not out.exists():
            failures.append(f"{key}: {out.name} missing, run `run` first")
            continue
        ours_all = read_csv(out)
        for source in chain["sources"]:
            stem = Path(source["pdf"]).stem
            ours = [r for r in ours_all if r["source_file"] == source["pdf"]]
            gt = ground_truth_file(ground_truth, stem)
            if gt is not None:
                errata = {(e["item"], e["column"]) for e in errata_rows if e["file"] == gt.name}
                r = compare_ground_truth(read_csv(gt), ours, mapping, errata)
                print(f"{key} {stem}: ground truth {r['rows']} rows, recall {r['recall']:.1%}, "
                      f"{r['cells']} cells, {len(r['mismatches'])} mismatches")
                if not r["passed"]:
                    failures += [f"{key} {stem}: unmatched row {n}" for n in r["unmatched"]]
                    failures += [f"{key} {stem}: {m}" for m in r["mismatches"]]
            gold = golden / f"{stem}.csv"
            if gold.exists():
                msgs = compare_golden(read_csv(gold), ours)
                print(f"{key} {stem}: golden {len(read_csv(gold))} rows, {len(msgs)} failures")
                failures += [f"{key} {stem}: {m}" for m in msgs]
    return failures


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("manifest", help="page/text/parser report for every PDF -> work/manifest.csv")
    run_p = sub.add_parser("run", help="extract every approved chain -> outputs/<key>.csv")
    run_p.add_argument("--chain", help="only this chain key, e.g. 16_Beefeater")
    sub.add_parser("eval", help="compare outputs with ground truth and golden rows; exit 1 on any failure")
    args = parser.parse_args(argv)
    chains_file = ROOT / "config" / "chains.yaml"

    if args.cmd == "manifest":
        rows = manifest(ROOT / "inputs", chains_file, ROOT / "work" / "manifest.csv")
        print(f"{len(rows)} PDFs -> work/manifest.csv; parsers: {dict(Counter(r['parser'] for r in rows))}")
    elif args.cmd == "run":
        for path, rows in run(ROOT / "inputs", chains_file, ROOT / "outputs", args.chain).items():
            errors = sum("error:" in r["flags"] for r in rows)
            warns = sum("warn:" in r["flags"] for r in rows)
            print(f"{path.relative_to(ROOT)}: {len(rows)} rows, {errors} with errors, {warns} with warnings")
    elif args.cmd == "eval":
        failures = evaluate(chains_file, ROOT / "outputs", ROOT / "inputs" / "ground-truth",
                            ROOT / "golden", ROOT / "config")
        print("\n".join(failures) or "eval: all checks passed")
        sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
```

Replace `config/chains.yaml`. The six Whitbread sources are unchanged and stay `approved: true`; the new Five Guys source is `approved: false` until a person approves it in Step 6. The column list matches the PDF: nine values per serving, then the same nine per 100g.

```yaml
# Every chain Menu Tracker extracts, keyed by its Menu Tracker script key (menutracker.ipynb).
# Output: outputs/<key>.csv, one CSV per chain, merging all of its sources.
#
# Per source:
#   pdf       file name in inputs/
#   parser    name in pipeline/parsers/__init__.py PARSERS (one layout can serve many chains)
#   region    UK | NI | ROI
#   columns   (numeric_table only) the dictionary column of each numeric column, left to right
#   markers   the PDF's allergen key: printed marker -> Yes | May contain | No. Omit when the PDF has none.
#             "" = what an allergen with no marker means for this PDF ("No" only if the PDF says so).
#   disclaimer  menu-wide allergen statement, kept here (not in the CSV)
#   approved  set to true by a person after checking markers/disclaimer against the PDF

16_Beefeater:
  chain: Beefeater
  sources:
    - pdf: beefeater_ss25_breakfast_menu_allergy_nutrition_v1.pdf
      parser: premier_inn_breakfast
      region: UK
      category: breakfast
      # The guide "covers the following major allergens" and lists each item's Contains / May Contain.
      markers: { '': 'No' }
      disclaimer: >-
        We take great care to prevent cross-contamination when preparing your order in our kitchens.
        However, due to the layout and operation of our kitchens we do not have specific allergen free
        zones and it is therefore not possible to fully guarantee separation of allergens. There is
        significant risk of cross-contamination in our buffet areas and deep fat fryers.
      approved: true
    - pdf: beefeater_ss25_drinks_menu_allergy_nutrition_v1.pdf
      parser: whitbread_drinks_grid
      region: UK
      category: drinks
      # Key: "Y  The allergen is present". The guide "declares allergens intentionally added only"
      # and "does not include any 'may contains'", so no mark = not an ingredient.
      markers: { 'Y': 'Yes', '': 'No' }
      disclaimer: >-
        Our allergen information sheet does not include any “may contains” information where provided by
        our suppliers. Our kitchens also handle numerous ingredients and allergens and whilst we have
        strict controls in place to reduce the risk of contamination, unfortunately, it is not possible
        for us to guarantee that our dishes will be 100% allergen free. There is also significant risk
        of cross contamination from our fryers.
      approved: true

17_Brewersfayre:
  chain: Brewers Fayre
  sources:
    - pdf: brewers_fayre_allergy_nutrition_ss25_breakfast_menu.pdf
      parser: premier_inn_breakfast
      region: UK
      category: breakfast
      # The guide "covers the following major allergens" and lists each item's Contains / May Contain.
      markers: { '': 'No' }
      disclaimer: >-
        We take great care to prevent cross-contamination when preparing your order in our kitchens.
        However, due to the layout and operation of our kitchens we do not have specific allergen free
        zones and it is therefore not possible to fully guarantee separation of allergens. There is
        significant risk of cross-contamination in our buffet areas and deep fat fryers.
      approved: true
    - pdf: brewers_fayre_allergy_nutrition_ss25_drinks_menu.pdf
      parser: whitbread_drinks_grid
      region: UK
      category: drinks
      # Key: "Y  The allergen is present". The guide "declares allergens intentionally added only"
      # and "does not include any 'may contains'", so no mark = not an ingredient.
      markers: { 'Y': 'Yes', '': 'No' }
      disclaimer: >-
        Our allergen information sheet does not include any “may contains” information where provided by
        our suppliers. Our kitchens also handle numerous ingredients and allergens and whilst we have
        strict controls in place to reduce the risk of contamination, unfortunately, it is not possible
        for us to guarantee that our dishes will be 100% allergen free. There is also significant risk
        of cross contamination from our fryers.
      approved: true

21_TableTable:
  chain: Table Table
  sources:
    - pdf: table_table_allergy_nutrition_ss25_breakfast_menu.pdf
      parser: premier_inn_breakfast
      region: UK
      category: breakfast
      # The guide "covers the following major allergens" and lists each item's Contains / May Contain.
      markers: { '': 'No' }
      disclaimer: >-
        We take great care to prevent cross-contamination when preparing your order in our kitchens.
        However, due to the layout and operation of our kitchens we do not have specific allergen free
        zones and it is therefore not possible to fully guarantee separation of allergens. There is
        significant risk of cross-contamination in our buffet areas and deep fat fryers.
      approved: true
    - pdf: table_table_allergy_nutrition_ss25_drinks_menu.pdf
      parser: whitbread_drinks_grid
      region: UK
      category: drinks
      # Key: "Y  The allergen is present". The guide "declares allergens intentionally added only"
      # and "does not include any 'may contains'", so no mark = not an ingredient.
      markers: { 'Y': 'Yes', '': 'No' }
      disclaimer: >-
        Our allergen information sheet does not include any “may contains” information where provided by
        our suppliers. Our kitchens also handle numerous ingredients and allergens and whilst we have
        strict controls in place to reduce the risk of contamination, unfortunately, it is not possible
        for us to guarantee that our dishes will be 100% allergen free. There is also significant risk
        of cross contamination from our fryers.
      approved: true

52_FiveGuys:
  chain: Five Guys
  sources:
    - pdf: nutrition.pdf
      parser: numeric_table
      region: UK                # "UK LOCATIONS ONLY"
      category: food
      # No allergen information in this PDF, so no `markers` and the CSV has no allergen columns.
      # Columns left to right: nine values per serving, then the same nine per 100g.
      columns:
        - energykJ_Per Portion
        - energykCal_Per Portion
        - fat_Per Portion
        - saturates_Per Portion
        - carbohydrates_Per Portion
        - sugars_Per Portion
        - fibre_Per Portion
        - protein_Per Portion
        - salt_Per Portion
        - energykJ_Per 100g/ml
        - energykCal_Per 100g/ml
        - fat_Per 100g/ml
        - saturates_Per 100g/ml
        - carbohydrates_Per 100g/ml
        - sugars_Per 100g/ml
        - fibre_Per 100g/ml
        - protein_Per 100g/ml
        - salt_Per 100g/ml
      approved: false
```

- [ ] **Step 4: Run the full test suite**

Run: `uv run pytest -v` Expected: 89 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/cli.py config/chains.yaml tests/test_cli.py tests/test_ingest.py
git commit -m "feat: Five Guys chain through the numeric-table parser"
```

- [ ] **Step 6: Approval by a person**

Ask the person to check the `52_FiveGuys` source in `config/chains.yaml` against `inputs/nutrition.pdf`:
1. The 18 `columns` match the PDF's column order: kJ, kcal, total fat, saturates, carbohydrates, sugars, fibre, protein, salt per serving, then the same nine per 100g.
2. No allergen information is printed in the PDF, so there is no `markers`.

Then they set `approved: true`. Don't set it yourself.

After approval run:

- `uv run python -m pipeline.cli run`. Expected, in addition to the three Phase 1 lines unchanged:

  ```
  outputs/52_FiveGuys.csv: 54 rows, 4 with errors, 5 with warnings
  ```

  The 9 flagged rows come from the PDF's own numbers (Lettuce 58 kJ but 19 kcal, Relish 0.2 saturates but 0 fat, and so on). Pearl Scan has the same values.

- `uv run python -m pipeline.cli eval`. Expected: the Five Guys line `52_FiveGuys nutrition: ground truth 54 rows, recall 100.0%, 972 cells, 0 mismatches`, the Phase 1 lines unchanged, then `eval: all checks passed`, exit code 0.

- [ ] **Step 7: Commit the approval**

```bash
git add config/chains.yaml
git commit -m "chore: approve the Five Guys source"
```

---

## Next slices (separate plans, per spec §10)

- **2b: Pizza Express** (PEX UK, BEL NI): the same layout, but needs character-level extraction (`pdfplumber`, a decision first) and per-table column positions.
- **2c onward:** Starbucks, Coffee #1, Pizza Hut, Odeon, Cineworld, Domino's.

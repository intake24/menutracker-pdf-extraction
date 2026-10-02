# Phase 2b: Pizza Express (pdfplumber, per-table columns) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce `11_PizzaExpress.csv` from the UK (`PEX-…`) and Northern Ireland (`BEL-…`) PDFs, checked against Pearl Scan ground truth (818 rows, 14,724 nutrient cells).

**Architecture:**
- The `numeric_table` parser from slice 2a now takes its words from pdfplumber, which separates cells that are printed almost touching; poppler returned `1232` and `11.1` as one word.
- A `header` option gives each table on a page its own column positions and takes section names from its column-header block.
- A `wrapped_names` option joins long names that wrap onto a second line.
- Page titles persist as a parent in `Category`.
- `eval` pairs repeated item names with Pearl Scan's by order of occurrence.
- No LLM calls.

**Tech Stack:** Python 3.12, `uv`, `pydantic` v2, `pyyaml`, `pdfplumber` (new, approved 2026-10-01), `pytest`, poppler.

**Spec:** [docs/pipeline-design.md](../../pipeline-design.md), draft v3. This plan implements slice 2b of §10. The Pizza Express findings are in §2 and the decision in §12 (Q13).

## Global Constraints

- Git holds code, `schemas/`, `config/` and `golden/` only. Data (`inputs/`, `outputs/`, `samples/`, `work/`) is gitignored. Tests read PDFs and ground truth from the local `inputs/`.
- Runtime dependencies: `pydantic>=2.9`, `pyyaml>=6`, and `pdfplumber` (new in this slice, approved by the user). Dev dependency: `pytest>=8`. Add nothing else.
- No LLM or network calls.
- **Extract, don't transform.** Cells are written exactly as printed, as strings. No unit or basis conversion, nothing derived.
- A PDF with no allergen information produces no allergen columns, and its source has no `markers`.
- Anything the parser can't place raises: an unreadable cell, a cell under no column, text between rows, a wrong column count. It is never guessed at or dropped.
- Row problems go into `flags` and values are never changed. Flags can come from the **source**: the Pizza Express PDFs print figures that fail the arithmetic checks.
- `run` refuses a chain with any source not marked `approved: true` (skipping it with a notice unless named). Only a person sets `approved: true`.
- Existing behaviour is unchanged: the Phase 1 chains and Five Guys produce the same rows as before.

## Review Focus

1. **Cells printed almost touching.** PEX page 19 prints `1232` and `11.1` 0.8 pt apart. Expected: two cells in their own columns, never one value like `123211.1`. Tests: Task 1 `test_fine_words_split_cells_that_poppler_returns_as_one_word`; Task 3 `test_pizza_express_cells_printed_touching_are_split`.
2. **Several tables on one page that share the last column but not the first** (PEX page 19). Expected: each row uses its own table's columns, never another table's. Tests: Task 3 `test_tables_on_one_page_that_share_the_last_column_each_use_their_own_columns`, `test_pizza_express_every_item_with_its_section`.
3. **Wrapped names, including on the first row of a table.** Expected: joined into one name when enabled; never lost, never swallowed into the section name; too far away, or not enabled, raises. Tests: Task 3 `test_wrapped_name_is_joined_when_enabled_and_raises_otherwise`, `test_a_wrapped_name_on_the_first_row_of_a_table_is_not_swallowed_into_the_section`, `test_a_name_only_line_too_far_above_a_row_is_not_a_wrapped_name`.
4. **Column-header text leaking into the section name** (`Starters – Dough Balls (kcal)`). Expected: only the text left of the numeric columns. Test: Task 3 `test_section_comes_from_the_header_block_and_column_header_text_is_left_out`.
5. **Repeated item names in the ground truth** (the same item in several sections, or twice in one). Expected: paired one-to-one by order, and a lost duplicate shows as unmatched, not hidden. Test: Task 2 `test_repeated_names_pair_up_by_order_of_occurrence`.
6. **Figures in the PDF that fail the arithmetic checks.** Expected: flagged, value unchanged, and the two regions kept apart. Test: Task 4 `test_pizza_express_merges_the_uk_and_northern_ireland_pdfs_and_keeps_regions_apart`.

---

## File Structure

| Path | Change | Responsibility |
|---|---|---|
| `pyproject.toml`, `uv.lock` | modify | Add `pdfplumber` |
| `pipeline/ingest.py` | modify | `page_words_fine`: words with digit runs split at character gaps |
| `pipeline/evaluate.py` | modify | Pair repeated names with the ground truth by order of occurrence |
| `pipeline/parsers/numeric_table.py` | modify | `header`, `wrapped_names`, per-table columns, parent titles; words from pdfplumber |
| `config/chains.yaml` | modify | Add `11_PizzaExpress` (UK and NI sources) |
| `README.md` | modify | Status and the new dependency |
| `tests/test_ingest.py`, `tests/test_evaluate.py`, `tests/test_numeric_table.py`, `tests/test_cli.py` | modify | Tests |

---

### Task 1: pdfplumber and fine-grained words

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (via `uv add`), `pipeline/ingest.py` (replace the whole file)
- Test: `tests/test_ingest.py` (replace the whole file)

**Interfaces:**
- Consumes: nothing new.
- Produces: `pipeline.ingest.page_words_fine(pdf: Path, gap: float = 0.5) -> list[list[Word]]`, the same `Word` type as `page_words`, with every run of digits split wherever two characters are more than `gap` pt apart.

- [ ] **Step 1: Add the dependency**

Run: `uv add pdfplumber` Expected: `pyproject.toml` gains `"pdfplumber>=0.11.10"` (or a newer floor) under `dependencies`; `uv.lock` updates; pdfminer.six, pypdfium2, pillow and cryptography are installed.

- [ ] **Step 2: Write the failing tests**

Replace `tests/test_ingest.py`; the two new tests are the last two.

`tests/test_ingest.py`:

```python
from pathlib import Path

from pipeline.ingest import load_chains, manifest_row, page_texts, page_words, page_words_fine, sources_by_pdf, text_sha

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


def test_fine_words_split_cells_that_poppler_returns_as_one_word():
    pdf = INPUTS / "PEX-Nutritional-Menu---May-2025.ashx.pdf"
    assert any(w.text == "123211.1" for w in page_words(pdf)[18])           # poppler: two cells, one word
    texts = [w.text for w in page_words_fine(pdf)[18]]
    assert "123211.1" not in texts and "1232" in texts and "11.1" in texts   # pdfplumber, by character gap


def test_fine_words_keep_ordinary_words_whole():
    texts = {w.text for w in page_words_fine(INPUTS / "PEX-Nutritional-Menu---May-2025.ashx.pdf")[10]}
    assert {"Goats", "Cheese", "Buddha", "Bowl"} <= texts
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_ingest.py -v` Expected: FAIL at collection with `ImportError: cannot import name 'page_words_fine' from 'pipeline.ingest'`.

- [ ] **Step 4: Implement**

Replace `pipeline/ingest.py`:

```python
import hashlib
import html
import re
import subprocess
from pathlib import Path
from typing import NamedTuple

import pdfplumber
import yaml

CHAINS_FILE = Path(__file__).resolve().parent.parent / "config" / "chains.yaml"
IMAGE_PAGE_MAX_CHARS = 200  # non-whitespace chars; below this the page is treated as image-only
WORD = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>')


class Word(NamedTuple):
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


def page_texts(pdf: Path) -> list[str]:
    """Layout-preserving text, one string per page (pdftotext ends every page with a form feed)."""
    out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                         check=True, capture_output=True, text=True).stdout
    return out.split("\f")[:-1]


def page_words(pdf: Path) -> list[list[Word]]:
    """Every word with its bounding box (points, origin top-left), one list per page."""
    out = subprocess.run(["pdftotext", "-bbox", str(pdf), "-"],
                         check=True, capture_output=True, text=True).stdout
    return [[Word(float(a), float(b), float(c), float(d), html.unescape(t)) for a, b, c, d, t in WORD.findall(page)]
            for page in out.split("<page ")[1:]]


NUMERIC_CHARS = re.compile(r"^[\d.<]+$")


def page_words_fine(pdf: Path, gap: float = 0.5) -> list[list[Word]]:
    """Words like page_words, but runs of digits are split wherever two characters are more than `gap` pt apart."""
    out = []
    with pdfplumber.open(pdf) as doc:
        for page in doc.pages:
            coarse = page.extract_words(x_tolerance=3, y_tolerance=3)
            fine = page.extract_words(x_tolerance=gap, y_tolerance=3)
            words = []
            for w in coarse:
                if NUMERIC_CHARS.match(w["text"]):
                    inside = [f for f in fine if f["x0"] >= w["x0"] - 0.1 and f["x1"] <= w["x1"] + 0.1
                              and abs(f["top"] - w["top"]) < 1]
                    words += [Word(f["x0"], f["top"], f["x1"], f["bottom"], f["text"]) for f in inside]
                else:
                    words.append(Word(w["x0"], w["top"], w["x1"], w["bottom"], w["text"]))
            out.append(words)
    return out


def text_sha(pages: list[str]) -> str:
    return hashlib.sha256("\f".join(pages).encode()).hexdigest()[:16]


def load_chains(path: Path = CHAINS_FILE) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def sources_by_pdf(chains: dict) -> dict[str, list[tuple[str, dict]]]:
    """pdf filename -> [(chain_key, source), ...]; one PDF can feed several chains."""
    out: dict[str, list[tuple[str, dict]]] = {}
    for key, chain in chains.items():
        for source in chain["sources"]:
            out.setdefault(source["pdf"], []).append((key, source))
    return out


def manifest_row(pdf: Path, chains: dict) -> dict:
    pages = page_texts(pdf)
    sizes = [len("".join(p.split())) for p in pages]
    users = sources_by_pdf(chains).get(pdf.name, [])
    return {
        "file": pdf.name,
        "pages": len(pages),
        "chars": sum(sizes),
        "text_sha": text_sha(pages),
        "chains": " ".join(key for key, _ in users),
        "parser": " ".join(sorted({s["parser"] for _, s in users})) or "unassigned",
        "image_pages": " ".join(str(i) for i, n in enumerate(sizes, start=1) if n < IMAGE_PAGE_MAX_CHARS),
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_ingest.py -v` Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock pipeline/ingest.py tests/test_ingest.py
git commit -m "feat: pdfplumber word extraction that splits touching cells"
```

---

### Task 2: Pair repeated names with the ground truth by order

**Files:**
- Modify: `pipeline/evaluate.py` (replace the whole file)
- Test: `tests/test_evaluate.py` (replace the whole file)

**Interfaces:**
- Consumes: nothing new.
- Produces: `compare_ground_truth` now pairs rows that share a normalised name one-to-one in order of occurrence (1st with 1st, 2nd with 2nd); an extra ground-truth row beyond ours is `unmatched`. Signatures are unchanged.

- [ ] **Step 1: Write the failing test**

Replace `tests/test_evaluate.py`; the new test is the last one.

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


def test_repeated_names_pair_up_by_order_of_occurrence():
    truth = [{"item_name": "Margherita", "kcal": "100"}, {"item_name": "Margherita", "kcal": "200"}]
    ours = [{"Product_Name": "Margherita", "Size": "", "energykCal_Per Portion": "100"},
            {"Product_Name": "Margherita", "Size": "", "energykCal_Per Portion": "200"}]
    mapping = {"item_name": "Product_Name", "kcal": "energykCal_Per Portion"}
    assert compare_ground_truth(truth, ours, mapping, set())["passed"]
    swapped = compare_ground_truth(truth, ours[::-1], mapping, set())
    assert not swapped["passed"] and len(swapped["mismatches"]) == 2
    lost = compare_ground_truth(truth, ours[:1], mapping, set())
    assert lost["unmatched"] == ["Margherita"] and not lost["passed"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_evaluate.py -v` Expected: `test_repeated_names_pair_up_by_order_of_occurrence` FAILS (the second `Margherita` is compared with the first row); the other 7 pass.

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
    by_key: dict[str, list[dict]] = {}
    for r in ours:
        by_key.setdefault(norm(r["Product_Name"] + r.get("Size", "")), []).append(r)
    seen: dict[str, int] = {}   # repeated names pair up by order of occurrence: 1st with 1st, 2nd with 2nd
    unmatched, mismatches, cells = [], [], 0
    for t in truth:
        name = t["item_name"]
        if (name, "*") in errata:
            continue
        key = norm(name)
        n = seen[key] = seen.get(key, -1) + 1
        o = by_key.get(key, [])[n] if n < len(by_key.get(key, [])) else None
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

Run: `uv run pytest tests/test_evaluate.py -v` Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/evaluate.py tests/test_evaluate.py
git commit -m "fix: pair repeated names with the ground truth by order of occurrence"
```

---

### Task 3: `numeric_table` for Pizza Express

What the real PDFs (`PEX-…`, 25 pages, 453 items; `BEL-…`, 21 pages, 365 items) need, found against Pearl Scan:
- **Cells touching.** Page 19 prints `1232` and `11.1` 0.8 pt apart (Task 1).
- **Several tables per page.** Page 19 has a Piccolo table and a Pasta table. They share the right-hand columns but their per-portion columns start at different x, so each table needs its own columns.
- **Column-header blocks.** Each table starts with a block of header lines containing the word `Energy`. The section name (`Starters – Dough Balls`) is in a larger font in the middle of the block, on its own line. Header words over the numeric columns (`(kcal)`) must not leak into it.
- **A page title.** Page 22 has `Breakfast (selected restaurants only)` above the table; Pearl Scan prefixes it to every later section. Every page also has `PER PORTION PER 100g`, which is not a title (it contains digits).
- **Wrapped names.** `Goats Cheese & Beetroot Buddha Bowl with dough` / `sticks 854 3574 …`: the figures are on the second line.
- **Blank cells.** `Oasis Summer Fruits` has no fibre value.

**Files:**
- Modify: `pipeline/parsers/numeric_table.py` (replace the whole file)
- Test: `tests/test_numeric_table.py` (replace the whole file)

**Interfaces:**
- Consumes: `Word` and `page_words_fine` (Task 1).
- Produces:
  - `parse(pdf, source) -> list[dict]`, reading `source["columns"]` (required), `source.get("header")` and `source.get("wrapped_names", False)`.
  - `parse_pages(pages, columns, header=None, wrapped_names=False) -> list[dict]`.
  - Same row keys as slice 2a. `Category` is `parent - section` when a page title was seen.
  - Without `header` the behaviour of slice 2a is unchanged, except that tables are now told apart by where their last column ends, so a page may hold more than one.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_numeric_table.py`. Two slice 2a tests change: `test_a_second_table_with_different_columns_on_the_page_raises` becomes `test_without_headers_a_table_ending_elsewhere_is_read_with_its_own_columns`, and the geometry of `test_two_cells_in_one_column_raise` is fixed. Everything from `# --- header blocks` onward is new.

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
    a, b = parse_pages([p1, p2], COLUMNS, header="Energy")
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
PEX_SOURCE = {"columns": PEX_COLUMNS, "header": "Energy", "wrapped_names": True}


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_numeric_table.py -v` Expected: `9 failed, 25 passed, 4 errors`. The failures are the header, title, wrapped-name and per-table tests (`parse_pages() got an unexpected keyword argument 'header'`, or wrong categories) plus `test_without_headers_a_table_ending_elsewhere_is_read_with_its_own_columns`; the 4 `test_pizza_express_*` tests error because the parse itself raises. The slice 2a Five Guys tests still pass.

- [ ] **Step 3: Implement**

Replace `pipeline/parsers/numeric_table.py`:

```python
"""Generic parser for "item name followed by a row of numbers" nutrition tables (Five Guys, Pizza Express, ...).

Columns are found by position, not by counting tokens: the right edges of a table's numeric cells are clustered
into columns and `source["columns"]` names them left to right. That keeps a row with blank cells, e.g. an item with
per-100g values only, in the right columns. Words come from pdfplumber, which separates cells that are printed
almost touching (`1232` and `11.1`) where poppler returns one word.

Source options (config/chains.yaml):
  columns        the dictionary column of each numeric column, left to right (required)
  header         a word that marks a column-header line, e.g. "Energy". Enables several tables per page, each with
                 its own columns, and takes the section name from the header block (the text left of the columns)
  wrapped_names  join a name-only line directly above a data row onto that row's name

Without `header`, sections are ALL-CAPS heading lines at the left margin. Anything the parser can't place, an
unreadable cell, a cell under no column, text between rows, raises instead of being guessed at.
"""
import re
from collections import Counter
from pathlib import Path

from pipeline.ingest import Word, page_words_fine

NUMBER = re.compile(r"^(?:<\s?)?\d+(?:\.\d+)?$|^(?:Negligible|Traces?|Tr)$")
MIN_NUMBERS = 3          # a line needs this many trailing numeric cells to be a data row
SECTION_INDENT = 12      # section headings start at the left margin; wrapped text and notes are indented more
VALUELIKE = re.compile(r"\d|^(?:-|–|N/?A)$", re.I)   # a token that looks like a cell value, readable or not
NOTE_START = ("-", "*", "†")                          # a line starting like this is a note, not a name
LINE_GAP = 3             # words whose vertical centres are this close are on one line
WRAP_LINES = 1.5         # a name-only line within this many line heights above a data row continues its name
TABLE_GAP = 20           # without header lines: last-cell right edges further apart than this are different tables
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


def _tables(found: list[tuple[int, list[Word]]], header_lines: list[int]) -> list[list[tuple[int, list[Word]]]]:
    """Split the data rows into tables: by the header lines before them, or, without headers, by where their
    last cell ends (the rows of one table end at the same x)."""
    if header_lines:
        by_header: dict[int, list] = {}
        for item in found:
            by_header.setdefault(sum(h < item[0] for h in header_lines), []).append(item)
        return list(by_header.values())
    ordered = sorted(found, key=lambda f: f[1][-1].x1)
    groups = [[ordered[0]]]
    for item in ordered[1:]:
        if item[1][-1].x1 - groups[-1][-1][1][-1].x1 > TABLE_GAP:
            groups.append([])
        groups[-1].append(item)
    return groups


def _classify(lines: list[list[Word]], tables: list[list[float]], table_of: dict[int, list[float]],
              header_lines: list[int]) -> list[list[float] | None]:
    """For each line: the column anchors of its table if it is a data row (at least MIN_NUMBERS value-like words
    in that table's columns), else None."""
    kinds = []
    for i, line in enumerate(lines):
        n = sum(h < i for h in header_lines)
        candidates = [table_of[n]] if header_lines and n in table_of else tables
        best = None
        for anchors in candidates:
            cells = [w for w in line if w.x1 >= anchors[0] - COLUMN_GAP]
            if (sum(bool(VALUELIKE.search(w.text)) for w in cells) >= MIN_NUMBERS
                    and cells[-1].x1 <= anchors[-1] + COLUMN_GAP
                    and (best is None or abs(cells[-1].x1 - anchors[-1]) < abs(cells[-1].x1 - best[-1]))):
                best = anchors
        kinds.append(best)
    return kinds


def _row(line: list[Word], lead: list[Word], anchors: list[float], columns: list[str], category: str,
         page_no: int) -> dict:
    edge = anchors[0] - COLUMN_GAP                         # words wholly left of this are the name
    name = [w for w in line if w.x1 < edge]
    if not name:
        raise ValueError(f"page {page_no}: numbers without a name: {' '.join(w.text for w in line)!r}")
    product = " ".join(w.text for w in lead + name)
    row = {"Product_Name": product, "Category": category, "source_page": page_no}
    for w in (w for w in line if w.x1 >= edge):
        if not NUMBER.match(w.text):
            raise ValueError(f"page {page_no}: unreadable cell {w.text!r} in row {product!r}")
        nearest = min(range(len(anchors)), key=lambda j: abs(anchors[j] - w.x1))
        if abs(anchors[nearest] - w.x1) > COLUMN_GAP:
            raise ValueError(f"page {page_no}: {w.text!r} in row {product!r} is under no column")
        if columns[nearest] in row:
            raise ValueError(f"page {page_no}: two cells in column {columns[nearest]!r} in row {product!r}")
        row[columns[nearest]] = w.text
    return row


def parse_pages(pages: list[list[Word]], columns: list[str], header: str | None = None,
                wrapped_names: bool = False) -> list[dict]:
    rows = []
    parent = section = ""   # parent: a page title that persists ("Breakfast (selected restaurants only)")
    for page_no, words in enumerate(pages, start=1):
        lines = _lines(words)
        split = [_split(line) for line in lines]
        found = [(i, cells) for i, (name, cells) in enumerate(split) if name and len(cells) >= MIN_NUMBERS]
        if not found:
            continue
        header_lines = [i for i, line in enumerate(lines) if header and any(w.text == header for w in line)]
        # One set of columns per table, from the table's most common row width, so a row with blank cells
        # can't create or hide a column.
        tables: list[list[float]] = []
        table_of: dict[int, list[float]] = {}   # number of header lines before the table -> its column anchors
        for group in _tables(found, header_lines):
            usual = Counter(len(cells) for _, cells in group).most_common(1)[0][0]
            anchors = _anchors([c for _, cells in group if len(cells) == usual for c in cells])
            if len(anchors) != len(columns):
                raise ValueError(f"page {page_no}: found {len(anchors)} numeric columns, config names {len(columns)}")
            tables.append(anchors)
            table_of[sum(h < group[0][0] for h in header_lines)] = anchors
        kinds = _classify(lines, tables, table_of, header_lines)
        data = [i for i, anchors in enumerate(kinds) if anchors]
        if not data:
            raise ValueError(f"page {page_no}: rows with numbers were found but none fit the table's columns")
        first_row, last_row = data[0], data[-1]
        left = min(split[i][0][0].x0 for i, _ in found)

        # Where the table starts: at its first header line, else at the headings and notes directly above its
        # first row. Anything earlier is page furniture.
        start = first_row
        if header_lines and header_lines[0] < first_row:
            start = header_lines[0]
            titles = [" ".join(w.text for w in line) for line in lines[:start]]
            parent = " ".join(t for t in titles if not any(c.isdigit() for c in t)) or parent   # not "PER 100g"
        else:
            while start > 0 and kinds[start - 1] is None and (
                    _heading(lines[start - 1], left) or " ".join(w.text for w in lines[start - 1]).startswith(NOTE_START)):
                start -= 1

        in_header = False
        block: list[list[Word]] = []     # lines of the current column-header block
        pending: list[list[Word]] = []   # name-only lines waiting for the data row they continue
        for i in range(start, len(lines)):
            line, anchors = lines[i], kinds[i]
            text = " ".join(w.text for w in line)
            if header and any(w.text == header for w in line):
                block = block if in_header else []
                block.append(line)
                in_header, pending = True, []   # a title above a column header ("PER PORTION PER 100g") is not a name
            elif anchors is None:
                if in_header:
                    block.append(line)
                elif heading := _heading(line, left):
                    section = heading
                elif i < last_row and not text.startswith(NOTE_START):
                    if not wrapped_names:
                        raise ValueError(f"page {page_no}: text between rows that is not a heading or note "
                                         f"(a wrapped name?): {text!r}")
                    pending.append(line)
            else:
                if in_header:
                    # The section name is the header-block text left of the numeric columns, level with the
                    # column headers. Text below the last column header is the start of this row's name.
                    edge = anchors[0] - 2 * COLUMN_GAP
                    bottom = max(w.y1 for l in block for w in l if w.x1 >= edge)
                    above = [l for l in block if l[0].y0 < bottom]
                    section = " ".join(w.text for l in above for w in l if w.x1 < edge) or section
                    pending = [l for l in block if l[0].y0 >= bottom]
                    in_header = False
                    if pending and not wrapped_names:
                        raise ValueError(f"page {page_no}: text between the column headers and the first row "
                                         f"(a wrapped name?): {' '.join(w.text for w in pending[0])!r}")
                lead: list[Word] = []
                if pending:
                    if line[0].y0 - pending[-1][0].y0 > WRAP_LINES * (line[0].y1 - line[0].y0):
                        raise ValueError(f"page {page_no}: text above a row is too far away to be a wrapped name: "
                                         f"{' '.join(w.text for w in pending[-1])!r}")
                    lead, pending = [w for l in pending for w in l], []
                rows.append(_row(line, lead, anchors, columns, " - ".join(c for c in (parent, section) if c), page_no))
    return rows


def parse(pdf: Path, source: dict) -> list[dict]:
    return parse_pages(page_words_fine(pdf), source["columns"], source.get("header"), source.get("wrapped_names", False))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_numeric_table.py -v` Expected: 38 passed (about 5 s: the Pizza Express tests read real PDFs).

- [ ] **Step 5: Commit**

```bash
git add pipeline/parsers/numeric_table.py tests/test_numeric_table.py
git commit -m "feat: numeric-table parser handles header blocks, several tables per page and wrapped names"
```

---

### Task 4: Pizza Express chain, README, end to end

**Files:**
- Modify: `config/chains.yaml` (replace the whole file), `README.md` (replace the whole file)
- Test: `tests/test_cli.py` (replace), `tests/test_ingest.py` (replace)

**Interfaces:**
- Consumes: `numeric_table` with `header` and `wrapped_names` (Task 3), the order-based matcher (Task 2).
- Produces: `11_PizzaExpress` in `config/chains.yaml`, two sources in one chain: `UK` and `NI`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_cli.py`:

`tests/test_cli.py`:

```python
from pathlib import Path

import pytest

from pipeline.cli import SourceNotApproved, evaluate, run

ROOT = Path(__file__).resolve().parent.parent
ROWS = {"11_PizzaExpress": 818, "16_Beefeater": 207, "17_Brewersfayre": 207, "21_TableTable": 207, "52_FiveGuys": 54}
SOURCE_FLAGS = ("error: kJ/kcal", "error: saturates >", "error: sugars >", "warn: Atwater", "error: duplicate")   # the PDFs print these


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
        if path.stem in ("11_PizzaExpress", "52_FiveGuys"):   # their PDFs contain figures that fail the checks
            assert all(f.startswith(SOURCE_FLAGS) for r in flagged for f in r["flags"].split(" | "))
        else:
            assert not flagged
        assert {r["method"] for r in rows} == {"parser"}
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
        run(ROOT / "inputs", chains_file(tmp_path, approved=False), tmp_path / "out", "16_Beefeater")


def test_two_chains_sharing_a_pdf_each_get_their_own_column_mapping(tmp_path):
    import yaml
    chains = yaml.safe_load((ROOT / "config" / "chains.yaml").read_text())
    five = chains["52_FiveGuys"]["sources"][0] | {"approved": True}
    reverse = dict(five, columns=list(reversed(five["columns"])))
    cf = tmp_path / "chains.yaml"
    cf.write_text(yaml.safe_dump({"52_FiveGuys": {"chain": "A", "sources": [five]},
                                  "99_Reversed": {"chain": "B", "sources": [reverse]}}))
    written = run(ROOT / "inputs", cf, tmp_path / "out")
    by_chain = {p.stem: {r["Product_Name"]: r for r in rows} for p, rows in written.items()}
    assert by_chain["52_FiveGuys"]["Bacon"]["energykJ_Per Portion"] == "323"
    assert by_chain["99_Reversed"]["Bacon"]["energykJ_Per Portion"] == "6.6"   # the last printed cell


def test_run_skips_unapproved_chains_with_a_notice_but_refuses_when_asked_for_one(tmp_path, capsys):
    import yaml
    chains = yaml.safe_load((ROOT / "config" / "chains.yaml").read_text())
    for key, chain in chains.items():   # whatever is committed, Five Guys is the only unapproved chain here
        for source in chain["sources"]:
            source["approved"] = key != "52_FiveGuys"
    cf = tmp_path / "chains.yaml"
    cf.write_text(yaml.safe_dump(chains))
    written = run(ROOT / "inputs", cf, tmp_path / "out")
    assert sorted(p.stem for p in written) == sorted(k for k in ROWS if k != "52_FiveGuys")
    assert "skipped 52_FiveGuys: not approved" in capsys.readouterr().err
    with pytest.raises(SourceNotApproved):
        run(ROOT / "inputs", cf, tmp_path / "out", "52_FiveGuys")
    assert evaluate(cf, tmp_path / "out", ROOT / "inputs" / "ground-truth", ROOT / "golden", ROOT / "config") == []


def test_pizza_express_merges_the_uk_and_northern_ireland_pdfs_and_keeps_regions_apart(tmp_path):
    written = run(ROOT / "inputs", chains_file(tmp_path, approved=True), tmp_path / "out", "11_PizzaExpress")
    [(path, rows)] = written.items()
    by_region = {region: [r for r in rows if r["region"] == region] for region in ("UK", "NI")}
    assert {k: len(v) for k, v in by_region.items()} == {"UK": 453, "NI": 365}
    assert {r["source_file"] for r in by_region["NI"]} == {"BEL-Nutritional-Menu---May-2025.ashx.pdf"}
    header = path.read_text().splitlines()[0].split(",")
    assert "milk" not in header and "energykJ_Per 100g/ml" in header
    dupes = [r for r in rows if "duplicate" in r["flags"]]   # the PDF lists Smoky BBQ Chicken twice, in each region
    assert sorted((r["region"], r["Product_Name"]) for r in dupes) == [("NI", "Smoky BBQ Chicken"), ("UK", "Smoky BBQ Chicken")]
```

Replace `tests/test_ingest.py`; the only change from Task 1 is that the chains test now expects five chains:

`tests/test_ingest.py`:

```python
from pathlib import Path

from pipeline.ingest import load_chains, manifest_row, page_texts, page_words, page_words_fine, sources_by_pdf, text_sha

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


def test_one_pdf_per_source_and_five_chains_configured():
    chains = load_chains()
    assert set(chains) == {"11_PizzaExpress", "16_Beefeater", "17_Brewersfayre", "21_TableTable", "52_FiveGuys"}
    assert all(len(users) == 1 for users in sources_by_pdf(chains).values())


def test_image_only_pages_reported():
    row = manifest_row(INPUTS / "nutritional-information.pdf", {})
    assert row["chains"] == "" and row["parser"] == "unassigned"
    assert len(row["image_pages"].split()) == 79


def test_fine_words_split_cells_that_poppler_returns_as_one_word():
    pdf = INPUTS / "PEX-Nutritional-Menu---May-2025.ashx.pdf"
    assert any(w.text == "123211.1" for w in page_words(pdf)[18])           # poppler: two cells, one word
    texts = [w.text for w in page_words_fine(pdf)[18]]
    assert "123211.1" not in texts and "1232" in texts and "11.1" in texts   # pdfplumber, by character gap


def test_fine_words_keep_ordinary_words_whole():
    texts = {w.text for w in page_words_fine(INPUTS / "PEX-Nutritional-Menu---May-2025.ashx.pdf")[10]}
    assert {"Goats", "Cheese", "Buddha", "Bowl"} <= texts
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cli.py tests/test_ingest.py -v` Expected: `4 failed, 10 passed`, because `11_PizzaExpress` doesn't exist yet: `test_run_writes_one_csv_per_chain_and_passes_eval`, `test_run_skips_unapproved_chains_with_a_notice_but_refuses_when_asked_for_one`, `test_pizza_express_merges_the_uk_and_northern_ireland_pdfs_and_keeps_regions_apart` and `test_one_pdf_per_source_and_five_chains_configured`.

- [ ] **Step 3: Implement**

Replace `config/chains.yaml`. The six Whitbread sources and Five Guys are unchanged and stay `approved: true`; the two new Pizza Express sources are `approved: false` until a person approves them in Step 6. The two sources share one column list through a YAML anchor.

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

11_PizzaExpress:
  chain: Pizza Express
  sources:
    - pdf: PEX-Nutritional-Menu---May-2025.ashx.pdf
      parser: numeric_table
      region: UK                # "England, Wales & Scotland"
      category: food
      # No allergen information in these PDFs, so no `markers` and the CSV has no allergen columns.
      header: Energy            # each table has a column-header block; its left-hand text is the section name
      wrapped_names: true       # long names wrap onto a second line
      # Columns left to right: nine values per portion, then the same nine per 100g.
      columns: &pizza_express_columns
        - energykCal_Per Portion
        - energykJ_Per Portion
        - fat_Per Portion
        - saturates_Per Portion
        - carbohydrates_Per Portion
        - sugars_Per Portion
        - fibre_Per Portion
        - protein_Per Portion
        - salt_Per Portion
        - energykCal_Per 100g/ml
        - energykJ_Per 100g/ml
        - fat_Per 100g/ml
        - saturates_Per 100g/ml
        - carbohydrates_Per 100g/ml
        - sugars_Per 100g/ml
        - fibre_Per 100g/ml
        - protein_Per 100g/ml
        - salt_Per 100g/ml
      approved: false
    - pdf: BEL-Nutritional-Menu---May-2025.ashx.pdf
      parser: numeric_table
      region: NI                # "Northern Ireland"
      category: food
      header: Energy
      wrapped_names: true
      columns: *pizza_express_columns
      approved: false

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
      region: UK # "UK LOCATIONS ONLY"
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
      approved: true
```

Replace `README.md`:

```markdown
# menutracker-pdf-extraction

Turns the allergen and nutrition PDFs that Menu Tracker scrapes from UK food chains into CSVs, replacing the paid Pearl Scan (human) process. One CSV per chain, one row per food, drink or product.

Design: [docs/pipeline-design.md](docs/pipeline-design.md). Implementation plans: [docs/superpowers/plans/](docs/superpowers/plans/).

## Quick start

Needs Python 3.12, [uv](https://docs.astral.sh/uv/) and poppler (`pdftotext`). `uv sync` installs the Python dependencies, including pdfplumber.

```bash
uv sync uv run pytest                              # tests read PDFs from inputs/ (not in git) uv run python -m pipeline.cli manifest     # which parser each PDF in inputs/ uses -> work/manifest.csv uv run python -m pipeline.cli run          # -> outputs/<id>_<Chain>.csv uv run python -m pipeline.cli eval         # compare outputs with Pearl Scan and golden rows; exit 1 on failure
```

`run` only builds chains whose sources are all `approved: true` in `config/chains.yaml`; any other chain is skipped with a notice on stderr, or refused with an error if you name it with `--chain`. `eval` skips unapproved chains too.

## Where things live

| Path | In git? | What |
|---|---|---|
| `inputs/` | no | The PDFs. `inputs/ground-truth/<Chain>/` holds Pearl Scan's CSVs. |
| `outputs/` | no | The generated chain CSVs. |
| `config/chains.yaml` | yes | Every chain: its PDFs, which layout parser reads each, region, allergen marker key, approval. |
| `schemas/columns.yaml` | yes | The column dictionary shared by every chain CSV. |
| `pipeline/parsers/` | yes | One parser per PDF **layout** (several chains can share one). |
| `golden/` | yes | See below. |
| `config/ground_truth_errata.yaml` | yes | Known Pearl Scan mistakes, each confirmed against the PDF. |

## Output rules

- Values are written **exactly as the PDF prints them**: no unit or basis conversion, `Trace` / `<0.1` / `Negligible` kept as text.
- Allergen cells are `Yes`, `May contain`, `No` (only when the PDF declares the allergen absent) or blank (the PDF doesn't say). Each source's marker key lives in `config/chains.yaml`; an unknown marker stops the run.
- Problems go into a `flags` column and values are never changed. Flags can come from the PDF itself: some print figures that fail the kJ/kcal or saturates ≤ fat checks.

## How output is checked

`eval` runs two checks.

**Nutrition vs Pearl Scan.** Each PDF's output is compared with its newest Pearl Scan CSV in `inputs/ground-truth/`. At least 99% of its rows must match and every matched cell must agree, except confirmed Pearl Scan errors listed in the errata file. Pearl Scan has no allergen data, so allergens use the second check.

**Allergens vs `golden/`.** Each file in `golden/` is a **hand-picked sample of a few rows**, not a full copy of the PDF. A person checked those rows' allergen cells against the rendered PDF. `eval` requires them to match exactly. They are a spot check that marks land in the right columns, so a golden file with 6 rows for a 148-item PDF is normal. The full output is in `outputs/`.

## Adding a chain

1. Find the chain's key in Menu Tracker's `menutracker.ipynb` (e.g. `16_Beefeater`).
2. Add it to `config/chains.yaml` with each PDF, its layout `parser`, `region`, and (if the PDF has allergen information) the `markers` key, copied from the PDF's own key.
3. Use an existing parser if the layout matches. Otherwise add one in `pipeline/parsers/` and register it in `pipeline/parsers/__init__.py`.
4. Run `eval`. Add `golden/<pdf-stem>.csv` rows for the allergen cells and check them against the PDF by eye.
5. A person sets `approved: true`.

## Status

| Done | Chains |
|---|---|
| Phase 1 | Beefeater, Brewers Fayre, Table Table |
| Phase 2a | Five Guys |
| Phase 2b | Pizza Express (UK and Northern Ireland PDFs) |

Next: the other text-based layouts. Vue, Papa John's and Krispy Kreme need a vision route because their text layers are unusable. See §10 of the design doc.
```

- [ ] **Step 4: Run the full test suite**

Run: `uv run pytest -v` Expected: 122 passed (about 25 s).

- [ ] **Step 5: Commit**

```bash
git add config/chains.yaml README.md tests/test_cli.py tests/test_ingest.py
git commit -m "feat: Pizza Express chain (UK and Northern Ireland) through the numeric-table parser"
```

- [ ] **Step 6: Approval by a person**

Ask the person to check both `11_PizzaExpress` sources in `config/chains.yaml` against their PDFs:
1. The 18 `columns` match the printed order: kcal, kJ, fat, saturates, carbohydrates, sugars, fibre, protein, salt per portion, then the same nine per 100g. Note that kcal comes before kJ here, unlike Five Guys.
2. `UK` is `PEX-…` ("England, Wales & Scotland") and `NI` is `BEL-…` ("Northern Ireland").
3. Neither PDF has allergen information, so there is no `markers`.

Then they set `approved: true` on both. Don't set it yourself.

After approval run:

- `uv run python -m pipeline.cli run`. Expected, in addition to the Phase 1 and Five Guys lines unchanged:

  ```
  outputs/11_PizzaExpress.csv: 818 rows, 34 with errors, 31 with warnings
  ```

  The flagged rows come from the PDFs' own figures (kJ not matching kcal, sugars above carbohydrates, and so on). Pearl Scan has the same values. `Smoky BBQ Chicken` is listed twice in each region with different values and is flagged as a duplicate.

- `uv run python -m pipeline.cli eval`. Expected: `11_PizzaExpress PEX-Nutritional-Menu---May-2025.ashx: ground truth 453 rows, recall 100.0%, 8154 cells, 0 mismatches`, the same for `BEL-…` with `365 rows` and `6570 cells`, the earlier lines unchanged, then `eval: all checks passed`, exit code 0.

- [ ] **Step 7: Commit the approval**

```bash
git add config/chains.yaml
git commit -m "chore: approve the Pizza Express sources"
```

---

## Next slices (separate plans, per spec §10)

- **2c onward:** Starbucks (2 PDFs), Coffee #1, Pizza Hut (`●`/`○` matrix), Odeon (nutrition and pre-packed matrices, three regions), Cineworld (`✓`/`▲` matrix), Domino's.
- **Phase 3:** the vision route for Vue, Papa John's and Krispy Kreme; then LLM text for menu layouts.

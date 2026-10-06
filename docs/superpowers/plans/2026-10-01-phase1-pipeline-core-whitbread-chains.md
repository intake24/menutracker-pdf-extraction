> **Historical plan.** Kept as a record of how the work was planned; the state of the project is in `docs/start-here.md` and `docs/end-of-round-report-2026-10.md`.

# Phase 1: Pipeline Core + Beefeater, Brewers Fayre, Table Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared pipeline core and the first two PDF layouts, so that `run` writes three complete chain CSVs (`16_Beefeater.csv`, `17_Brewersfayre.csv`, `21_TableTable.csv`) and `eval` confirms them against Pearl Scan ground truth (nutrition) and hand-verified golden rows (allergens).

**Architecture:**
- poppler's `pdftotext` provides layout text (`-layout`) and word coordinates (`-bbox`).
- A parser per PDF *layout* turns that into rows that use the shared column dictionary (`schemas/columns.yaml`), with values exactly as printed.
- `config/chains.yaml` maps each chain to its source PDFs, layout parser, region and allergen marker key.
- `run` merges each chain's sources into one CSV and records problems in `flags`.
- `eval` compares the output with the Pearl Scan CSVs in `inputs/ground-truth/` and with `golden/`.
- No LLM calls in this phase.

**Tech Stack:** Python 3.12, `uv`, `pydantic` v2, `pyyaml`, `pytest`, poppler (`pdftotext`).

**Spec:** [docs/pipeline-design.md](../../pipeline-design.md), draft v2. This plan implements rollout Phase 1 (§10). The decisions it follows are in §12.

## Global Constraints

- Git holds code, `schemas/`, `config/` and `golden/` only. Data (`inputs/`, `outputs/`, `samples/`, `work/`) is gitignored and never committed. Tests read the PDFs and ground truth from the local `inputs/`.
- Python `>=3.12`, managed with `uv`. Run everything through `uv run ...`.
- Runtime dependencies: `pydantic>=2.9` and `pyyaml>=6` only. Dev dependency: `pytest>=8`. Add nothing else.
- `pdftotext` (poppler) must be on `PATH`. It's installed at `/opt/homebrew/bin/pdftotext`.
- No LLM or network calls in this phase.
- **Extract, don't transform.** Values are written exactly as the PDF prints them (strings, e.g. `"698"`, `"0.41"`, `"Negligible"`). No unit or basis conversion, and nothing derived.
- Allergen cells are exactly `Yes`, `May contain`, `No` or blank.
  - `No` only when the source's key declares absence: `markers[""] == "No"`.
  - Blank means the PDF doesn't say.
- Allergen wording or markers not in the code or config raise `UnknownAllergen`. They are never skipped.
- Output is one CSV per chain: `outputs/<chain key>.csv`, where the key comes from `config/chains.yaml` (e.g. `16_Beefeater`).
  - Columns are the dictionary columns that have a value, in dictionary order, followed by `region, source_file, source_page, method, flags`.
- `run` refuses a chain with any source not marked `approved: true`. Only a person sets `approved: true`.
- Row problems are never dropped and values are never changed. Every issue goes into `flags` with the prefix `error:` or `warn:`.

## Review Focus

1. **Allergen wording or markers the code doesn't know** ("Lupine", "Gluten Free", a `P` in a `Y` grid). Expected: a loud `UnknownAllergen` that names the item, never a silently blank or `No` cell. Tests: Task 2 `test_unknown_term_raises`, Task 5 `test_unknown_allergen_names_item`, Task 6 `test_unknown_marker_raises`.
2. **An item's allergen block split across a page break.** Expected: one row with every allergen, and `source_page` set to the page holding the nutrition line. Test: Task 5 `test_block_split_across_page_break`.
3. **"SEE PACKAGING LABEL FOR ALLERGENS" sections.** Expected: their allergen cells are blank (not stated), never `No`, and the next heading doesn't nest under them. Test: Task 6 `test_see_label_section_is_not_stated_and_does_not_nest`.
4. **A grid mark that sits under no allergen column** (layout drift in a new edition). Expected: a loud `ValueError` naming the page and position, never a mark assigned to the nearest column. Test: Task 6 `test_mark_outside_any_column_raises`.
5. **An item with allergens but no nutrition line.** Expected: the row is still exported with `flags` = `error: no nutrition line found`. Test: Task 5 `test_item_without_nutrition_is_flagged`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml`, `.gitignore` | uv project, pytest config; keep data out of git |
| `schemas/columns.yaml` | Column dictionary: names, order, nutrient words |
| `config/chains.yaml` | Chain key → sources (pdf, parser, region, markers, disclaimer, approved) |
| `config/pearlscan_columns.yaml` | Pearl Scan column → our column, for `eval` |
| `config/ground_truth_errata.yaml` | Confirmed Pearl Scan errors (empty for now) |
| `golden/<pdf-stem>.csv` | Hand-verified allergen rows, one file per distinct PDF |
| `pipeline/columns.py` | Load the dictionary; build the Pydantic row model |
| `pipeline/allergens.py` | "Contains / May Contain" text → allergen cells |
| `pipeline/validate.py` | Arithmetic checks, duplicate detection |
| `pipeline/export.py` | `finalise` (validate + flag) and per-chain `write_csv` |
| `pipeline/ingest.py` | `pdftotext` text and word boxes, text hash, chains config, manifest row |
| `pipeline/parsers/premier_inn_breakfast.py` | Premier Inn breakfast guide layout |
| `pipeline/parsers/whitbread_drinks_grid.py` | Whitbread pub drinks allergen grid layout |
| `pipeline/parsers/__init__.py` | `PARSERS` registry |
| `pipeline/evaluate.py` | Ground-truth and golden comparison |
| `pipeline/cli.py` | `manifest`, `run`, `eval` |
| `tests/test_*.py` | One test file per module |

Deliberately left out of Phase 1, as listed in the spec's §10:
- The LLM routes and repair (Phase 3).
- The review/overrides loop (Phase 4).
- The per-portion vs per-100 g ratio check, added with the first layout that has both bases.
- Basis-synonym mapping, added with the first layout that prints a basis other than "Per Portion".

---

### Task 1: Project scaffold, column dictionary and row model

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `schemas/columns.yaml`, `pipeline/__init__.py`, `pipeline/columns.py`
- Test: `tests/test_columns.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `pipeline.columns.PROVENANCE: list[str]`, equal to `["region", "source_file", "source_page", "method", "flags"]`.
  - `ALLERGEN_VALUES = ("Yes", "May contain", "No")`.
  - `@dataclass Columns(version: int, types: dict[str, str], nutrient_words: list[str], bases: list[str])`.
    - `types` maps each column to `"text"`, `"nutrient"` or `"allergen"`, in output order.
    - The property `.allergens -> list[str]` lists the allergen columns.
  - `load_columns(path: Path = COLUMNS_FILE) -> Columns`.
  - `build_row_model(columns: Columns) -> type[BaseModel]`. The model validates dicts keyed by column name, requires `Product_Name`, and rejects unknown columns.

- [ ] **Step 1: Keep data out of git**

Only code, schemas, config and golden rows go into git. The repo has no commits yet, and the data under `inputs/`, `outputs/` and `samples/` is already staged. Unstage it; the files stay on disk:

```bash
git rm -r --cached --quiet inputs outputs samples .DS_Store
git status --short   # expect: no inputs/, outputs/, samples/ entries
```

- [ ] **Step 2: Create the project files**

`pyproject.toml`:

```toml
[project]
name = "menutracker-pdf-extraction"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["pydantic>=2.9", "pyyaml>=6"]

[dependency-groups]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

`.gitignore`:

```
# Data: kept local, never committed. schemas/, config/ and golden/ ARE committed.
inputs/
outputs/
samples/
work/
.DS_Store

# Python
.venv/
__pycache__/
.pytest_cache/
```

`pipeline/__init__.py`: an empty file.

`schemas/columns.yaml`:

```yaml
# Column dictionary shared by every chain CSV. Order here = column order in every CSV.
# A chain CSV contains only the columns that have a value for that chain.
# Names start from samples/3_CostaCoffee.csv. Add a column here before any parser emits it.
version: 1
text_columns: [Product_Name, Product_Description, Size, Milk, CoffeeType, Ingredients,
               Category, Serving_Size, Serving_Size_Unit, Diet, notes]
bases: ["Per 100g/ml", "Per Portion", "Per Pizza", "Per Slice", "Per Product As Sold"]
nutrients: [carbohydrates, energykCal, energykJ, fat, fibre, protein, salt, saturates, sugars,
            vitaminB6, vitaminB12, vitaminC, zinc, sodium, caffeine]
# A nutrient cell holds the PDF's value as printed: a number, "<number", or one of these words.
nutrient_words: [Negligible, Trace, Traces, Tr]
allergens: [gluten, wheat, rye, barley, oats, spelt, kamut, celery, crustacean, egg, fish, lupin,
            milk, mollusc, mustard, peanut, sesame, soya, sulphite, treeNuts]
trailing_text_columns: [treeNutSource]
```

Run: `uv sync` Expected: creates `.venv/` and `uv.lock`, and installs pydantic, pyyaml and pytest.

- [ ] **Step 3: Write the failing tests**

`tests/test_columns.py`:

```python
import pytest
from pydantic import ValidationError

from pipeline.columns import build_row_model, load_columns


def test_dictionary_starts_with_costa_columns_in_order():
    cols = list(load_columns().types)
    assert cols[:6] == ["Product_Name", "Product_Description", "Size", "Milk", "CoffeeType", "Ingredients"]
    assert cols.index("energykJ_Per 100g/ml") < cols.index("energykJ_Per Portion") < cols.index("gluten")
    assert cols[-1] == "treeNutSource"
    assert load_columns().types["milk"] == "allergen"


@pytest.mark.parametrize("value", ["93", "0.41", "<0.1", "< 0.5", "Trace", "trace", "Negligible", "Tr"])
def test_nutrient_cells_accept_numbers_and_known_words(value):
    Row = build_row_model(load_columns())
    Row.model_validate({"Product_Name": "x", "fat_Per Portion": value})


@pytest.mark.parametrize("bad", [
    {"energykCal_Per Portion": "93"},              # missing Product_Name
    {"Product_Name": "x", "fat_Per Portion": "lots"},  # nutrient text not in the dictionary
    {"Product_Name": "x", "fat_Per Portion": "."},     # stray printing glitch is flagged, not guessed
    {"Product_Name": "x", "milk": "N"},            # allergen vocabulary is Yes / May contain / No
    {"Product_Name": "x", "Colour": "red"},        # column not in the dictionary
])
def test_row_model_rejects(bad):
    with pytest.raises(ValidationError):
        build_row_model(load_columns()).model_validate(bad)
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest tests/test_columns.py -v` Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.columns'`.

- [ ] **Step 5: Implement `pipeline/columns.py`**

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, create_model

COLUMNS_FILE = Path(__file__).resolve().parent.parent / "schemas" / "columns.yaml"
PROVENANCE = ["region", "source_file", "source_page", "method", "flags"]
ALLERGEN_VALUES = ("Yes", "May contain", "No")


@dataclass
class Columns:
    version: int
    types: dict[str, str]  # column -> "text" | "nutrient" | "allergen", in output order
    nutrient_words: list[str]
    bases: list[str]

    @property
    def allergens(self) -> list[str]:
        return [c for c, t in self.types.items() if t == "allergen"]


def load_columns(path: Path = COLUMNS_FILE) -> Columns:
    spec = yaml.safe_load(path.read_text())
    types = {c: "text" for c in spec["text_columns"]}
    for base in spec["bases"]:
        types |= {f"{n}_{base}": "nutrient" for n in spec["nutrients"]}
    types |= {a: "allergen" for a in spec["allergens"]}
    types |= {c: "text" for c in spec["trailing_text_columns"]}
    return Columns(spec["version"], types, spec["nutrient_words"], spec["bases"])


def nutrient_pattern(words: list[str]) -> str:
    return r"^(?:<\s?)?\d+(?:\.\d+)?$|^(?i:" + "|".join(words) + ")$"


def build_row_model(columns: Columns) -> type[BaseModel]:
    """Pydantic model keyed by CSV column name (aliases), rejecting unknown columns."""
    kinds = {
        "text": str,
        "nutrient": Annotated[str, StringConstraints(pattern=nutrient_pattern(columns.nutrient_words))],
        "allergen": Literal[ALLERGEN_VALUES],
    }
    fields = {"f0": (str, Field(alias="Product_Name"))}
    for i, (col, kind) in enumerate(columns.types.items(), start=1):
        if col != "Product_Name":
            fields[f"f{i}"] = (kinds[kind] | None, Field(default=None, alias=col))
    return create_model("Row", __config__=ConfigDict(extra="forbid"), **fields)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_columns.py -v` Expected: 14 passed.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock .gitignore schemas/columns.yaml pipeline/__init__.py pipeline/columns.py tests/test_columns.py
git commit -m "feat: column dictionary and pydantic row model"
```

---

### Task 2: Allergen text parser

**Files:**
- Create: `pipeline/allergens.py`
- Test: `tests/test_allergens.py`

**Interfaces:**
- Consumes: `load_columns()` (Task 1).
- Produces:
  - `ALLERGENS: list[str]`, the dictionary's allergen columns.
  - `class UnknownAllergen(ValueError)`.
  - `parse_allergens(contains: str, may_contain: str, unlisted: str) -> dict[str, str]`.
    - Returns every column in `ALLERGENS`: `"Yes"` or `"May contain"` where the text names the allergen, otherwise `unlisted` (`"No"` or `""`).
    - Also returns `"treeNutSource"`, formatted `"<yes nuts>; may: <may nuts>"`, when nuts are named.

- [ ] **Step 1: Write the failing tests**

`tests/test_allergens.py`:

```python
import pytest

from pipeline.allergens import ALLERGENS, UnknownAllergen, parse_allergens


def test_contains_and_may_contain_with_subtypes():
    got = parse_allergens(
        "Cereals containing Gluten (Wheat), Egg, Milk",
        "Other Cereals containing (Barley, Oats, Rye), Soya, Tree Nuts (Almond, Hazelnut)",
        unlisted="No",
    )
    assert {k: v for k, v in got.items() if v != "No"} == {
        "gluten": "Yes", "wheat": "Yes", "egg": "Yes", "milk": "Yes",
        "barley": "May contain", "oats": "May contain", "rye": "May contain",
        "soya": "May contain", "treeNuts": "May contain", "treeNutSource": "may: Almond, Hazelnut",
    }
    assert got["celery"] == "No" and got["spelt"] == "No"


def test_yes_beats_may_contain():
    got = parse_allergens("Cereals containing Gluten (Oats)", "Other Cereals containing (Barley, Wheat)", "No")
    assert got["gluten"] == "Yes" and got["oats"] == "Yes" and got["wheat"] == "May contain"


def test_no_major_allergens_uses_the_source_key():
    assert set(parse_allergens("No major allergens", "No major allergens", "No").values()) == {"No"}
    assert set(parse_allergens("No major allergens", "No major allergens", "").values()) == {""}
    assert set(parse_allergens("", "", "No")) == set(ALLERGENS)


def test_tree_nut_sources_both_levels():
    got = parse_allergens("Tree Nuts (Hazelnut)", "Tree Nuts (Almond)", "No")
    assert got["treeNuts"] == "Yes" and got["treeNutSource"] == "Hazelnut; may: Almond"


@pytest.mark.parametrize("text", ["Lupine", "Cereals containing Gluten (Corn)", "Gluten Free"])
def test_unknown_term_raises(text):
    with pytest.raises(UnknownAllergen):
        parse_allergens(text, "", "No")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_allergens.py -v` Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.allergens'`.

- [ ] **Step 3: Implement `pipeline/allergens.py`**

```python
import re

from pipeline.columns import load_columns

ALLERGENS = load_columns().allergens
CEREALS = {"wheat": "wheat", "rye": "rye", "barley": "barley", "oats": "oats", "oat": "oats",
           "spelt": "spelt", "kamut": "kamut", "khorasan": "kamut"}
SIMPLE = {"celery": "celery", "crustacean": "crustacean", "crustaceans": "crustacean",
          "egg": "egg", "eggs": "egg", "fish": "fish", "lupin": "lupin", "milk": "milk",
          "mollusc": "mollusc", "molluscs": "mollusc", "mustard": "mustard",
          "peanut": "peanut", "peanuts": "peanut", "sesame": "sesame", "soya": "soya", "soy": "soya",
          "sulphite": "sulphite", "sulphites": "sulphite", "sulphur dioxide": "sulphite"}
CEREAL_HEADS = {"cereals containing gluten", "other cereals containing", "gluten"}
NUT_HEADS = {"tree nuts", "nuts"}
NONE_PHRASES = {"", "no major allergens"}


class UnknownAllergen(ValueError):
    pass


def _lookup(table: dict[str, str], term: str) -> str:
    if term not in table:
        raise UnknownAllergen(f"unknown allergen term {term!r}")
    return table[term]


def _terms(text: str) -> list[tuple[str, list[str]]]:
    """'Cereals (Wheat, Oats), Egg' -> [('cereals', ['wheat', 'oats']), ('egg', [])]"""
    out = []
    for m in re.finditer(r"([^,(]+?)\s*(?:\(([^)]*)\))?\s*(?:,|$)", text.strip()):
        head = m.group(1).strip().lower()
        if head:
            subs = [s.strip().lower() for s in (m.group(2) or "").split(",") if s.strip()]
            out.append((head, subs))
    return out


def parse_allergens(contains: str, may_contain: str, unlisted: str) -> dict[str, str]:
    """Map 'Contains: ...' / 'May Contain: ...' text to allergen cells.

    `unlisted` is what the source's key says an allergen it doesn't list means: "No" when the
    guide declares it covers every major allergen, "" (not stated) otherwise.
    """
    result: dict[str, str] = {}
    nuts: dict[str, list[str]] = {"Yes": [], "May contain": []}
    # "May contain" first so "Yes" overwrites it when an allergen appears in both.
    for text, level in ((may_contain, "May contain"), (contains, "Yes")):
        if text.strip().lower() in NONE_PHRASES:
            continue
        for head, subs in _terms(text):
            if head in CEREAL_HEADS:
                keys = ["gluten"] + [_lookup(CEREALS, s) for s in subs]
            elif head in NUT_HEADS:
                keys = ["treeNuts"]
                nuts[level] += [s.title() for s in subs]
            else:
                keys = [_lookup(SIMPLE, head)]
            for k in keys:
                result[k] = level
    parts = []
    if nuts["Yes"]:
        parts.append(", ".join(nuts["Yes"]))
    if nuts["May contain"]:
        parts.append("may: " + ", ".join(nuts["May contain"]))
    if parts:
        result["treeNutSource"] = "; ".join(parts)
    return {a: unlisted for a in ALLERGENS} | result
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_allergens.py -v` Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/allergens.py tests/test_allergens.py
git commit -m "feat: parse Contains/May Contain allergen text"
```

---

### Task 3: Row checks and per-chain CSV export

**Files:**
- Create: `pipeline/validate.py`, `pipeline/export.py`
- Test: `tests/test_validate.py`, `tests/test_export.py`

**Interfaces:**
- Consumes: `PROVENANCE`, `Columns`, `build_row_model` and `load_columns` (Task 1).
- Produces:
  - `number(value) -> float | None`.
  - `check_row(row: dict) -> list[str]`: issue strings, each starting `error:` or `warn:`. Checks every dictionary basis and skips cells that aren't plain numbers.
  - `duplicate_issues(rows: list[dict], key_cols=("Product_Name", "Category", "Size", "Milk", "region")) -> dict[int, str]`.
  - `finalise(rows: list[dict], columns: Columns) -> list[dict]`: the same rows with `flags` set to every issue joined by `" | "`. Values are unchanged.
  - `write_csv(rows: list[dict], columns: Columns, path: Path) -> list[str]`: writes only the columns that have a value plus `PROVENANCE`, and returns the header.

- [ ] **Step 1: Write the failing tests**

`tests/test_validate.py`:

```python
from pipeline.validate import check_row, duplicate_issues


def portion(**nutrients):
    return {f"{k}_Per Portion": v for k, v in nutrients.items()}


CROISSANT = portion(energykJ="698", energykCal="167", fat="7.7", saturates="4.4",
                    carbohydrates="19.9", sugars="2.3", protein="3.8")


def test_clean_row():
    assert check_row(CROISSANT) == []


def test_kj_kcal_mismatch():
    assert any(i.startswith("error: kJ/kcal") for i in check_row(CROISSANT | portion(energykJ="900")))


def test_subset_errors():
    issues = check_row(CROISSANT | portion(saturates="8.0", sugars="25"))
    assert any("saturates > fat" in i for i in issues)
    assert any("sugars > carbohydrates" in i for i in issues)


def test_atwater_is_warning_only():
    issues = check_row(CROISSANT | portion(energykCal="300", energykJ="1255"))
    assert len(issues) == 1 and issues[0].startswith("warn: Atwater")


def test_tiny_values_no_false_alarm():
    sachet = portion(energykJ="16", energykCal="4", fat="0.0", saturates="0.0",
                     carbohydrates="0.9", sugars="0.0", protein="0.0")
    assert check_row(sachet) == []


def test_text_values_skip_arithmetic():
    assert check_row(CROISSANT | portion(fat="Negligible", saturates="Trace")) == []


def test_other_bases_checked():
    assert check_row({"energykJ_Per 100g/ml": "900", "energykCal_Per 100g/ml": "100"})


def test_duplicates():
    a = {"Product_Name": "Toast", "Category": "BAKERY", "energykCal_Per Portion": "90", "source_page": 1}
    assert duplicate_issues([a, a | {"source_page": 3}]) == {}
    assert list(duplicate_issues([a, a | {"energykCal_Per Portion": "95"}])) == [1]
    assert duplicate_issues([a | {"region": "UK"}, a | {"region": "NI", "energykCal_Per Portion": "95"}]) == {}
```

`tests/test_export.py`:

```python
import csv

from pipeline.columns import PROVENANCE, load_columns
from pipeline.export import finalise, write_csv


def test_finalise_flags_without_changing_values_then_write(tmp_path):
    columns = load_columns()
    rows = [
        {"Product_Name": "Toast", "energykJ_Per Portion": "393", "energykCal_Per Portion": "93",
         "milk": "Yes", "egg": "No", "region": "UK", "source_page": 2},
        {"Product_Name": "Jam", "egg": "N", "fat_Per Portion": "1", "saturates_Per Portion": "2",
         "region": "UK", "source_page": 3, "flags": "error: no nutrition line found"},
    ]
    out = finalise(rows, columns)
    assert out[0]["flags"] == "" and out[0]["energykCal_Per Portion"] == "93"
    assert "no nutrition line found" in out[1]["flags"]
    assert "saturates > fat" in out[1]["flags"] and "egg" in out[1]["flags"]
    assert out[1]["egg"] == "N"   # invalid values are kept for the reviewer, never silently changed

    header = write_csv(out, columns, tmp_path / "16_Test.csv")
    assert header == ["Product_Name", "energykCal_Per Portion", "energykJ_Per Portion", "fat_Per Portion",
                      "saturates_Per Portion", "egg", "milk", *PROVENANCE]  # only columns with a value
    with (tmp_path / "16_Test.csv").open(newline="") as f:
        written = list(csv.DictReader(f))
    assert written[0]["egg"] == "No" and written[0]["source_page"] == "2" and written[1]["milk"] == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_validate.py tests/test_export.py -v` Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.validate'`.

- [ ] **Step 3: Implement `pipeline/validate.py`**

```python
from pipeline.columns import PROVENANCE, load_columns

KJ_PER_KCAL = 4.184
BASES = load_columns().bases


def number(value) -> float | None:
    """The cell as a number, or None for blanks and words like 'Trace' or '<0.1'."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def check_row(row: dict) -> list[str]:
    """Arithmetic sanity checks on numeric cells. Absolute floors stop rounding on tiny values raising false alarms."""
    issues = []
    for base in BASES:
        def get(nutrient: str) -> float | None:
            return number(row.get(f"{nutrient}_{base}"))

        kj, kcal = get("energykJ"), get("energykCal")
        if kj is not None and kcal is not None and abs(kj - KJ_PER_KCAL * kcal) > max(0.03 * kj, 5):
            issues.append(f"error: kJ/kcal mismatch {base}: {kj:g} kJ vs {kcal:g} kcal")
        for part, whole in (("saturates", "fat"), ("sugars", "carbohydrates")):
            p, w = get(part), get(whole)
            if p is not None and w is not None and p > w + 0.05:
                issues.append(f"error: {part} > {whole} {base}: {p:g} > {w:g}")
        protein, carbs, fat = get("protein"), get("carbohydrates"), get("fat")
        if kcal is not None and None not in (protein, carbs, fat):
            estimate = 4 * protein + 4 * carbs + 9 * fat + 2 * (get("fibre") or 0)
            # warn only: alcohol (7 kcal/g) and polyols legitimately break this
            if abs(estimate - kcal) > max(0.15 * kcal, 10):
                issues.append(f"warn: Atwater {base}: stated {kcal:g} kcal, estimated {estimate:.0f}")
    return issues


def duplicate_issues(rows: list[dict],
                     key_cols: tuple[str, ...] = ("Product_Name", "Category", "Size", "Milk", "region")) -> dict[int, str]:
    def values(r: dict) -> dict:
        return {k: v for k, v in r.items() if k not in PROVENANCE}

    seen: dict[tuple, int] = {}
    out = {}
    for i, r in enumerate(rows):
        key = tuple(r.get(k) for k in key_cols)
        if key in seen and values(rows[seen[key]]) != values(r):
            out[i] = f"error: duplicate of row {seen[key]} with different values"
        seen.setdefault(key, i)
    return out
```

- [ ] **Step 4: Implement `pipeline/export.py`**

```python
import csv
from pathlib import Path

from pydantic import ValidationError

from pipeline.columns import PROVENANCE, Columns, build_row_model
from pipeline.validate import check_row, duplicate_issues


def finalise(rows: list[dict], columns: Columns) -> list[dict]:
    """Check every row against the column dictionary and the arithmetic checks; record all issues in `flags`.

    Values are never changed: rows that fail keep what the source said so a reviewer can see it.
    """
    model = build_row_model(columns)
    dupes = duplicate_issues(rows)
    out = []
    for i, row in enumerate(rows):
        data = {k: v for k, v in row.items() if k not in PROVENANCE and v not in (None, "")}
        issues = check_row(data)
        try:
            model.model_validate(data)
        except ValidationError as e:
            issues += [f"error: {'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
        if i in dupes:
            issues.append(dupes[i])
        flags = [row["flags"]] if row.get("flags") else []
        out.append(row | {"flags": " | ".join(flags + issues)})
    return out


def write_csv(rows: list[dict], columns: Columns, path: Path) -> list[str]:
    """Write one chain CSV with only the dictionary columns that have a value; returns the header."""
    used = [c for c in columns.types if c == "Product_Name" or any(r.get(c) not in (None, "") for r in rows)]
    header = used + PROVENANCE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        w.writerows({k: "" if v is None else v for k, v in r.items()} for r in rows)
    return header
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_validate.py tests/test_export.py -v` Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add pipeline/validate.py pipeline/export.py tests/test_validate.py tests/test_export.py
git commit -m "feat: row sanity checks and per-chain CSV export"
```

---

### Task 4: Ingest, chains config and the `manifest` command

**Files:**
- Create: `config/chains.yaml`, `pipeline/ingest.py`, `pipeline/cli.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `Word(NamedTuple)` with `x0, y0, x1, y1: float` (points, origin top-left) and `text: str`.
  - `page_texts(pdf: Path) -> list[str]`: one layout string per page.
  - `page_words(pdf: Path) -> list[list[Word]]`: one list of words per page.
  - `text_sha(pages: list[str]) -> str`: 16 hex characters.
  - `load_chains(path: Path = CHAINS_FILE) -> dict`.
  - `sources_by_pdf(chains: dict) -> dict[str, list[tuple[str, dict]]]`.
  - `manifest_row(pdf: Path, chains: dict) -> dict`, with keys `file, pages, chars, text_sha, chains, parser, image_pages`.
  - `pipeline.cli.main(argv=None)` and `pipeline.cli.manifest(inputs: Path, chains_file: Path, out: Path) -> list[dict]`.

- [ ] **Step 1: Create `config/chains.yaml`**

Chain keys come from Menu Tracker's `menutracker.ipynb` (`16_Beefeater`, `17_Brewersfayre`, `21_TableTable`). The disclaimers are copied word for word from each PDF's first page. Every source starts with `approved: false`; a person approves them in Task 7.

```yaml
# Every chain Menu Tracker extracts, keyed by its Menu Tracker script key (menutracker.ipynb).
# Output: outputs/<key>.csv, one CSV per chain, merging all of its sources.
#
# Per source:
#   pdf       file name in inputs/
#   parser    name in pipeline/parsers/__init__.py PARSERS (one layout can serve many chains)
#   region    UK | NI | ROI
#   markers   the PDF's allergen key: printed marker -> Yes | May contain | No.
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
      markers: {"": "No"}
      disclaimer: >-
        We take great care to prevent cross-contamination when preparing your order in our kitchens.
        However, due to the layout and operation of our kitchens we do not have specific allergen free
        zones and it is therefore not possible to fully guarantee separation of allergens. There is
        significant risk of cross-contamination in our buffet areas and deep fat fryers.
      approved: false
    - pdf: beefeater_ss25_drinks_menu_allergy_nutrition_v1.pdf
      parser: whitbread_drinks_grid
      region: UK
      category: drinks
      # Key: "Y  The allergen is present". The guide "declares allergens intentionally added only"
      # and "does not include any 'may contains'", so no mark = not an ingredient.
      markers: {"Y": "Yes", "": "No"}
      disclaimer: >-
        Our allergen information sheet does not include any “may contains” information where provided by
        our suppliers. Our kitchens also handle numerous ingredients and allergens and whilst we have
        strict controls in place to reduce the risk of contamination, unfortunately, it is not possible
        for us to guarantee that our dishes will be 100% allergen free. There is also significant risk
        of cross contamination from our fryers.
      approved: false

17_Brewersfayre:
  chain: Brewers Fayre
  sources:
    - pdf: brewers_fayre_allergy_nutrition_ss25_breakfast_menu.pdf
      parser: premier_inn_breakfast
      region: UK
      category: breakfast
      # The guide "covers the following major allergens" and lists each item's Contains / May Contain.
      markers: {"": "No"}
      disclaimer: >-
        We take great care to prevent cross-contamination when preparing your order in our kitchens.
        However, due to the layout and operation of our kitchens we do not have specific allergen free
        zones and it is therefore not possible to fully guarantee separation of allergens. There is
        significant risk of cross-contamination in our buffet areas and deep fat fryers.
      approved: false
    - pdf: brewers_fayre_allergy_nutrition_ss25_drinks_menu.pdf
      parser: whitbread_drinks_grid
      region: UK
      category: drinks
      # Key: "Y  The allergen is present". The guide "declares allergens intentionally added only"
      # and "does not include any 'may contains'", so no mark = not an ingredient.
      markers: {"Y": "Yes", "": "No"}
      disclaimer: >-
        Our allergen information sheet does not include any “may contains” information where provided by
        our suppliers. Our kitchens also handle numerous ingredients and allergens and whilst we have
        strict controls in place to reduce the risk of contamination, unfortunately, it is not possible
        for us to guarantee that our dishes will be 100% allergen free. There is also significant risk
        of cross contamination from our fryers.
      approved: false

21_TableTable:
  chain: Table Table
  sources:
    - pdf: table_table_allergy_nutrition_ss25_breakfast_menu.pdf
      parser: premier_inn_breakfast
      region: UK
      category: breakfast
      # The guide "covers the following major allergens" and lists each item's Contains / May Contain.
      markers: {"": "No"}
      disclaimer: >-
        We take great care to prevent cross-contamination when preparing your order in our kitchens.
        However, due to the layout and operation of our kitchens we do not have specific allergen free
        zones and it is therefore not possible to fully guarantee separation of allergens. There is
        significant risk of cross-contamination in our buffet areas and deep fat fryers.
      approved: false
    - pdf: table_table_allergy_nutrition_ss25_drinks_menu.pdf
      parser: whitbread_drinks_grid
      region: UK
      category: drinks
      # Key: "Y  The allergen is present". The guide "declares allergens intentionally added only"
      # and "does not include any 'may contains'", so no mark = not an ingredient.
      markers: {"Y": "Yes", "": "No"}
      disclaimer: >-
        Our allergen information sheet does not include any “may contains” information where provided by
        our suppliers. Our kitchens also handle numerous ingredients and allergens and whilst we have
        strict controls in place to reduce the risk of contamination, unfortunately, it is not possible
        for us to guarantee that our dishes will be 100% allergen free. There is also significant risk
        of cross contamination from our fryers.
      approved: false
```

- [ ] **Step 2: Write the failing tests**

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


def test_one_pdf_per_source_and_three_chains_configured():
    chains = load_chains()
    assert set(chains) == {"16_Beefeater", "17_Brewersfayre", "21_TableTable"}
    assert all(len(users) == 1 for users in sources_by_pdf(chains).values())


def test_image_only_pages_reported():
    row = manifest_row(INPUTS / "nutritional-information.pdf", {})
    assert row["chains"] == "" and row["parser"] == "unassigned"
    assert len(row["image_pages"].split()) == 79
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_ingest.py -v` Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.ingest'`.

- [ ] **Step 4: Implement `pipeline/ingest.py`**

```python
import hashlib
import html
import re
import subprocess
from pathlib import Path
from typing import NamedTuple

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

- [ ] **Step 5: Implement `pipeline/cli.py`** (only the `manifest` command for now; Task 7 replaces this file)

```python
import argparse
import csv
from collections import Counter
from pathlib import Path

from pipeline.ingest import load_chains, manifest_row

ROOT = Path(__file__).resolve().parent.parent


def manifest(inputs: Path, chains_file: Path, out: Path) -> list[dict]:
    chains = load_chains(chains_file)
    rows = [manifest_row(p, chains) for p in sorted(inputs.glob("*.pdf"))]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return rows


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("manifest", help="page/text/parser report for every PDF -> work/manifest.csv")
    args = parser.parse_args(argv)

    if args.cmd == "manifest":
        rows = manifest(ROOT / "inputs", ROOT / "config" / "chains.yaml", ROOT / "work" / "manifest.csv")
        print(f"{len(rows)} PDFs -> work/manifest.csv; parsers: {dict(Counter(r['parser'] for r in rows))}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the tests, then the command**

Run: `uv run pytest tests/test_ingest.py -v` Expected: 5 passed.

Run: `uv run python -m pipeline.cli manifest` Expected: `35 PDFs -> work/manifest.csv; parsers: {'unassigned': 29, 'premier_inn_breakfast': 3, 'whitbread_drinks_grid': 3}`. The PDF count can differ if `inputs/` has changed.

- [ ] **Step 7: Commit**

```bash
git add config/chains.yaml pipeline/ingest.py pipeline/cli.py tests/test_ingest.py
git commit -m "feat: pdftotext ingest, chains config, manifest command"
```

---

### Task 5: Premier Inn breakfast parser

The guide is published identically by Beefeater, Brewers Fayre and Table Table: 7 pages and 59 items. `pdftotext -layout` gives one block per item:

```
PREMIER INN BREAKFAST
 UNLIMITED CONTINENTAL - BAKERY (per item/slice) - V
       Croissant - V
       Contains: Cereals containing Gluten (Wheat), Egg, Milk             May Contain: Other Cereals containing (Barley, Oats, Rye),
                                                                          Soya, Tree Nuts (Almond, Hazelnut)
                                 Energy           Fat         Saturates        Carbohydrates        Sugars        Protein        Salt
         Per Portion:
                          698 kJ / 167 kcal      7.7 g           4.4 g             19.9 g            2.3 g          3.8 g       0.41 g
```

Facts, checked 2026-10-01:
- 59 `Contains:` lines, each with a `May Contain:` column, and 59 nutrition lines that all match `NUTRITION`.
- Page 1 is intro text, and a footer "Published on : March 27, 2025" appears on every page.
- "PREMIER INN BREAKFAST" is printed once and applies to every section.
- The guide states that it covers every major allergen, so an allergen it doesn't list is `No` (`markers: {"": "No"}`).
- The output matches all 590 nutrition and serving-size cells in Pearl Scan's ground truth (checked in Task 7).

**Files:**
- Create: `pipeline/parsers/premier_inn_breakfast.py`, `pipeline/parsers/__init__.py`
- Test: `tests/test_premier_inn_breakfast.py`

**Interfaces:**
- Consumes: `page_texts` (Task 4), and `parse_allergens` and `UnknownAllergen` (Task 2).
- Produces:
  - `parse(pdf: Path, source: dict) -> list[dict]`, which uses `source["markers"][""]` as the value for unlisted allergens.
  - `parse_pages(pages: list[str], unlisted: str) -> list[dict]`.
  - `PARSERS: dict[str, Callable[[Path, dict], list[dict]]]` in `pipeline/parsers/__init__.py`.
  - Row keys:
    - `Product_Name, Category, Serving_Size, Serving_Size_Unit, Diet`.
    - Every allergen column and, when nuts are named, `treeNutSource`.
    - `<nutrient>_Per Portion` for 8 nutrients, as strings.
    - `source_page`, and `flags` when there's a problem.

- [ ] **Step 1: Write the failing tests**

`tests/test_premier_inn_breakfast.py`:

```python
from pathlib import Path

import pytest

from pipeline.allergens import UnknownAllergen
from pipeline.parsers.premier_inn_breakfast import parse, parse_pages

PDF = Path(__file__).resolve().parent.parent / "inputs" / "beefeater_ss25_breakfast_menu_allergy_nutrition_v1.pdf"
SOURCE = {"markers": {"": "No"}}

MAY_COL = 70
ENERGY = "                 Energy      Fat      Saturates      Carbohydrates      Sugars      Protein      Salt"
NUTRITION = "                 698 kJ / 167 kcal      7.7 g      4.4 g      19.9 g      2.3 g      3.8 g      0.41 g"
HEADING = "UNLIMITED COOKED BREAKFAST (per item)"


def contains_line(contains: str, may: str) -> str:
    return f"{'      Contains: ' + contains:<{MAY_COL}}May Contain: {may}"


@pytest.fixture(scope="module")
def rows():
    return parse(PDF, SOURCE)


def test_every_item_parsed_without_flags(rows):
    assert len(rows) == 59  # = number of "Contains:" lines in the PDF
    assert not [r for r in rows if r.get("flags")]


def test_croissant(rows):
    croissant = next(r for r in rows if r["Product_Name"] == "Croissant")
    assert croissant["Category"] == "PREMIER INN BREAKFAST - UNLIMITED CONTINENTAL - BAKERY (per item/slice)"
    assert croissant["Diet"] == "V" and croissant["source_page"] == 2
    assert croissant["energykJ_Per Portion"] == "698" and croissant["salt_Per Portion"] == "0.41"
    assert croissant["soya"] == "May contain" and croissant["treeNutSource"] == "may: Almond, Hazelnut"
    assert croissant["celery"] == "No"


def test_amounts_move_to_serving_size_descriptions_stay(rows):
    by_name = {r["Product_Name"]: r for r in rows}
    assert (by_name["Kelloggs Muesli Fruit"]["Serving_Size"], by_name["Kelloggs Muesli Fruit"]["Serving_Size_Unit"]) == ("45", "g")
    assert "Weetabix (per 2 biscuits)" in by_name and by_name["Weetabix (per 2 biscuits)"]["Serving_Size"] == ""
    assert by_name["Black Pudding (per slice)"]["Diet"] == ""


def test_every_section_carries_the_menu_title(rows):
    assert all(r["Category"].startswith("PREMIER INN BREAKFAST - ") for r in rows)
    assert {r["Category"] for r in rows} >= {"PREMIER INN BREAKFAST - UNLIMITED COOKED BREAKFAST (per item)"}


def test_block_split_across_page_break():
    page1 = "\n".join([
        HEADING,
        "      Marmite Portions - VE          V",
        contains_line("Cereals containing Gluten (Barley, Oats, Rye,", "No major allergens"),
        " Published on : March 27, 2025",
    ])
    page2 = "\n".join(["      Wheat), Celery", ENERGY, "   Per Portion:", NUTRITION])
    [row] = parse_pages([page1, page2], "No")
    assert row["Product_Name"] == "Marmite Portions" and row["Diet"] == "VE"
    assert row["Category"] == "PREMIER INN BREAKFAST - UNLIMITED COOKED BREAKFAST (per item)"
    assert row["wheat"] == "Yes" and row["celery"] == "Yes" and row["egg"] == "No"
    assert row["source_page"] == 2


def test_item_without_nutrition_is_flagged():
    page = "\n".join([
        HEADING,
        "      Lonely Toast - V",
        contains_line("Egg", "No major allergens"),
        "      Hash Brown (per piece) - VE    V",
        contains_line("No major allergens", "No major allergens"),
        ENERGY, "   Per Portion:", NUTRITION,
    ])
    first, second = parse_pages([page], "No")
    assert first["Product_Name"] == "Lonely Toast" and first["egg"] == "Yes"
    assert first["flags"] == "error: no nutrition line found"
    assert second["Product_Name"] == "Hash Brown (per piece)" and "flags" not in second


def test_unknown_allergen_names_item():
    page = "\n".join([HEADING, "      Mystery Pie", contains_line("Lupine", "No major allergens"), ENERGY, NUTRITION])
    with pytest.raises(UnknownAllergen, match="Mystery Pie"):
        parse_pages([page], "No")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_premier_inn_breakfast.py -v` Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.parsers'`.

- [ ] **Step 3: Implement `pipeline/parsers/premier_inn_breakfast.py`**

```python
"""Premier Inn breakfast allergy & nutrition guide (served at Beefeater, Brewers Fayre, Table Table).

Each item is a block: name line, "Contains: ... May Contain: ..." (wrapping onto following lines in
either column), an "Energy ... Salt" header, then one per-portion nutrition line.
"""
import re
from pathlib import Path

from pipeline.allergens import UnknownAllergen, parse_allergens
from pipeline.ingest import page_texts

NUTRITION = re.compile(
    r"(?P<kj>\d+(?:\.\d+)?) kJ / (?P<kcal>\d+(?:\.\d+)?) kcal\s+(?P<fat>[\d.]+) g\s+(?P<sat>[\d.]+) g\s+"
    r"(?P<carb>[\d.]+) g\s+(?P<sugar>[\d.]+) g\s+(?P<protein>[\d.]+) g\s+(?P<salt>[\d.]+) g"
)
FIELDS = {"kj": "energykJ", "kcal": "energykCal", "fat": "fat", "sat": "saturates", "carb": "carbohydrates",
          "sugar": "sugars", "protein": "protein", "salt": "salt"}
DIET = re.compile(r"\s+-\s+(VE|V)\b.*$")   # " - VE      V" suffix (the trailing V is an icon)
AMOUNT = re.compile(r"\s*\(per (\d+(?:\.\d+)?)\s?(g|kg|ml|l|oz)\)")  # "(per 45g)" -> serving size
ITEM_INDENT = 4                            # headings are indented less than this, items more
TITLE = "PREMIER INN BREAKFAST"            # printed once on page 2; applies to every section


def _is_heading(text: str) -> bool:
    bare = re.sub(r"\(per [^)]*\)", "", text)
    return any(c.isalpha() for c in bare) and not any(c.islower() for c in bare)


def _split(line: str, col: int) -> tuple[str, str]:
    """Split a wrapped allergen line into its (contains, may contain) parts."""
    parts = re.split(r"\s{3,}", line.strip(), maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    indent = len(line) - len(line.lstrip())
    return ("", parts[0]) if indent >= col - 5 else (parts[0], "")


def _finish(item: dict, m: re.Match | None, page_no: int, unlisted: str) -> dict:
    line = item["name_line"]
    diet = DIET.search(line)
    name = DIET.sub("", line)
    amount = AMOUNT.search(name)
    row = {
        "Product_Name": AMOUNT.sub("", name).strip(),
        "Category": item["category"],
        "Serving_Size": amount.group(1) if amount else "",
        "Serving_Size_Unit": amount.group(2) if amount else "",
        "Diet": diet.group(1) if diet else "",
        "source_page": page_no,
    }
    try:
        row |= parse_allergens(" ".join(filter(None, item["contains"])), " ".join(filter(None, item["may"])),
                               unlisted)
    except UnknownAllergen as e:
        raise UnknownAllergen(f"{row['Product_Name']}: {e}") from e
    if m is None:
        row["flags"] = "error: no nutrition line found"
    else:
        row |= {f"{FIELDS[k]}_Per Portion": v for k, v in m.groupdict().items()}
    return row


def parse_pages(pages: list[str], unlisted: str) -> list[dict]:
    rows: list[dict] = []
    headings: list[str] = []   # current run of consecutive heading lines
    category = ""              # headings joined with " - "; a new run replaces it
    in_run = False
    item: dict | None = None   # item being read
    col: int | None = None     # column where "May Contain:" starts; set while reading allergen lines
    lines = [(page_no, line) for page_no, page in enumerate(pages, start=1) for line in page.splitlines()
             if line.strip() and not line.strip().startswith("Published on")]
    for i, (page_no, line) in enumerate(lines):
        text = line.strip()
        starts_item = i + 1 < len(lines) and lines[i + 1][1].strip().startswith("Contains:")
        if text.startswith("Contains:"):
            col = line.index("May Contain:")
            item["contains"] = [line[:col].strip().removeprefix("Contains:").strip()]
            item["may"] = [line[col:].strip().removeprefix("May Contain:").strip()]
            continue
        if m := NUTRITION.search(line):
            rows.append(_finish(item, m, page_no, unlisted))
            item, col = None, None
            continue
        if text.startswith(("Energy", "Per Portion:")):
            col = None
            continue
        if item is not None and col is not None and not starts_item:
            left, right = _split(line, col)
            item["contains"].append(left)
            item["may"].append(right)
            continue
        if item is not None and item["contains"]:   # previous item never got a nutrition line
            rows.append(_finish(item, None, page_no, unlisted))
            item, col = None, None
        if len(line) - len(line.lstrip()) < ITEM_INDENT:
            if _is_heading(text) and text != TITLE:
                headings = (headings if in_run else []) + [DIET.sub("", text).strip()]
                category, in_run = " - ".join([TITLE, *headings]), True
            continue
        item = {"name_line": text, "category": category, "contains": [], "may": []}
        in_run = False
    if item is not None and item["contains"]:
        rows.append(_finish(item, None, len(pages), unlisted))
    return rows


def parse(pdf: Path, source: dict) -> list[dict]:
    return parse_pages(page_texts(pdf), source["markers"][""])
```

`pipeline/parsers/__init__.py`:

```python
from pipeline.parsers import premier_inn_breakfast

# parser name (as used in config/chains.yaml) -> parse(pdf_path, source_config) -> rows
PARSERS = {
    "premier_inn_breakfast": premier_inn_breakfast.parse,
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_premier_inn_breakfast.py -v` Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/parsers/__init__.py pipeline/parsers/premier_inn_breakfast.py tests/test_premier_inn_breakfast.py
git commit -m "feat: Premier Inn breakfast guide parser"
```

---

### Task 6: Whitbread drinks grid parser

Pages 3–8 of each drinks PDF are an allergen grid with no nutrition.
- Item names are at x ≈ 61. Each allergen column has a rotated header label at a fixed x (Wheat ≈ 252, Rye ≈ 282, … Sulphite ≈ 552).
- A `Y` sits about 3 pt to the right of its column's label.
- Section headings are centred, at x > 240.
- The date and `Page n` footer are at y ≈ 558.
- The key says "Y = The allergen is present" and that the guide "declares allergens intentionally added only". So a cell with no mark is `No` (`markers: {"Y": "Yes", "": "No"}`).

Facts, checked 2026-10-01:

| PDF | Items | `Y` marks |
|---|---|---|
| Beefeater | 148 | 82 |
| Brewers Fayre | 148 | 83 |
| Table Table | identical to Brewers Fayre | |

- Sections whose heading says "SEE … LABEL FOR ALLERGENS" contain no items in these editions. The parser still treats them as "not stated" in case a future edition has items there.

**Files:**
- Create: `pipeline/parsers/whitbread_drinks_grid.py`
- Modify: `pipeline/parsers/__init__.py` (replace the whole file)
- Test: `tests/test_whitbread_drinks_grid.py`

**Interfaces:**
- Consumes: `page_words` and `Word` (Task 4), and `ALLERGENS` and `UnknownAllergen` (Task 2).
- Produces:
  - `parse(pdf: Path, source: dict) -> list[dict]`, using `source["markers"]`.
  - `parse_pages(pages: list[list[Word]], markers: dict[str, str]) -> list[dict]`.
  - Row keys: `Product_Name, Category`, every allergen column (`gluten` derived from the four cereal columns under the PDF's "Cereals Containing Gluten" group), `source_page`, and `treeNutSource` if printed.

- [ ] **Step 1: Write the failing tests**

`tests/test_whitbread_drinks_grid.py`:

```python
from collections import Counter
from pathlib import Path

import pytest

from pipeline.allergens import UnknownAllergen
from pipeline.ingest import Word
from pipeline.parsers.whitbread_drinks_grid import parse, parse_pages

INPUTS = Path(__file__).resolve().parent.parent / "inputs"
MARKERS = {"Y": "Yes", "": "No"}


def grid_page(*lines: tuple[float, list[tuple[float, str]]]) -> list[Word]:
    """A synthetic grid page: header labels at fixed x, then (y, [(x, text), ...]) lines."""
    header = [Word(146, 100, 160, 150, "Description"), Word(252, 160, 260, 190, "Wheat"),
              Word(282, 160, 290, 190, "Rye"), Word(312, 160, 320, 190, "Barley"),
              Word(342, 160, 350, 190, "Oat"), Word(432, 160, 440, 190, "Milk"),
              Word(552, 160, 560, 190, "Sulphite")]
    body = [Word(x, y, x + 8 * len(t), y + 8, t) for y, words in lines for x, t in words]
    return header + body


@pytest.mark.parametrize("pdf, items, marks", [
    ("beefeater_ss25_drinks_menu_allergy_nutrition_v1.pdf", 148, 82),
    ("brewers_fayre_allergy_nutrition_ss25_drinks_menu.pdf", 148, 83),
])
def test_every_item_and_mark_parsed(pdf, items, marks):
    rows = parse(INPUTS / pdf, {"markers": MARKERS})
    assert len(rows) == items
    yes = Counter(k for r in rows for k, v in r.items() if v == "Yes" and k != "gluten")
    assert sum(yes.values()) == marks  # every printed "Y" lands in exactly one allergen cell


def test_marks_land_in_their_columns():
    rows = parse(INPUTS / "beefeater_ss25_drinks_menu_allergy_nutrition_v1.pdf", {"markers": MARKERS})
    wine = next(r for r in rows if r["Product_Name"] == "JAM SHED, CHARDONNAY")
    assert {k for k, v in wine.items() if v == "Yes"} == {"egg", "milk", "fish", "sulphite"}
    assert wine["Category"] == "WINES - WHITE" and wine["spelt"] == ""  # grid has no spelt column: not stated
    carling = next(r for r in rows if r["Product_Name"] == "CARLING")
    assert carling["gluten"] == "Yes" and carling["barley"] == "Yes" and carling["oats"] == "No"


def test_headings_nest_until_an_item_appears():
    page = grid_page((220, [(380, "SPIRITS")]), (230, [(410, "GIN")]), (240, [(61, "HENDRICK'S")]),
                     (250, [(407, "VODKA")]), (260, [(61, "ABSOLUT"), (555, "Y")]))
    gin, vodka = parse_pages([page], MARKERS)
    assert gin["Category"] == "SPIRITS - GIN" and vodka["Category"] == "VODKA"
    assert vodka["sulphite"] == "Yes" and vodka["milk"] == "No" and vodka["gluten"] == "No"


def test_see_label_section_is_not_stated_and_does_not_nest():
    page = grid_page((220, [(300, "MIXERS - SEE PACKAGING LABEL FOR ALLERGENS")]), (230, [(61, "TONIC")]),
                     (240, [(400, "DRAUGHT")]), (250, [(61, "LAGER")]))
    tonic, lager = parse_pages([page], MARKERS)
    assert tonic["milk"] == "" and tonic["gluten"] == ""   # the grid gives no information here
    assert lager["Category"] == "DRAUGHT" and lager["milk"] == "No"


def test_unknown_marker_raises():
    page = grid_page((220, [(400, "BEERS")]), (230, [(61, "ODD ALE"), (315, "P")]))
    with pytest.raises(UnknownAllergen, match="ODD ALE"):
        parse_pages([page], MARKERS)


def test_mark_outside_any_column_raises():
    page = grid_page((220, [(400, "BEERS")]), (230, [(61, "ODD ALE"), (500, "Y")]))
    with pytest.raises(ValueError, match="under no allergen column"):
        parse_pages([page], MARKERS)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_whitbread_drinks_grid.py -v` Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.parsers.whitbread_drinks_grid'`.

- [ ] **Step 3: Implement `pipeline/parsers/whitbread_drinks_grid.py`**

```python
"""Whitbread pub drinks allergy guide (Beefeater, Brewers Fayre, Table Table): an allergen grid, no nutrition.

Pages 3+ hold a grid: item names on the left, one column per allergen with rotated header labels,
and a marker (e.g. "Y") in the cell when the allergen is present. Section headings are centred.
Columns are found from the x position of each header label, so marks are matched by position.
"""
import re
from pathlib import Path

from pipeline.allergens import ALLERGENS, UnknownAllergen
from pipeline.ingest import Word, page_words

LABELS = {"Wheat": "wheat", "Rye": "rye", "Barley": "barley", "Oat": "oats", "Soya": "soya", "Egg": "egg",
          "Milk": "milk", "Fish": "fish", "Crustacean": "crustacean", "Mollusc": "mollusc",
          "Sulphite": "sulphite", "Sesame": "sesame", "Celery": "celery", "Mustard": "mustard",
          "Peanut": "peanut", "Lupin": "lupin", "Nuts": "treeNuts", "Source": "treeNutSource"}
GRID_CEREALS = ["wheat", "rye", "barley", "oats"]   # the "Cereals Containing Gluten" column group
NAME_MAX_X = 240     # item names sit left of the first allergen column
COLUMN_TOLERANCE = 15
FOOTER = re.compile(r"^\d{2}/\d{2}/\d{4}$|^Page$")
NO_INFO = "LABEL FOR ALLERGENS"   # "... - SEE PACKAGING LABEL FOR ALLERGENS": the grid says nothing


def _lines(words: list[Word]) -> list[list[Word]]:
    rows: dict[int, list[Word]] = {}
    for w in words:
        rows.setdefault(round(w.y0), []).append(w)
    return [sorted(rows[y], key=lambda w: w.x0) for y in sorted(rows)]


def parse_pages(pages: list[list[Word]], markers: dict[str, str]) -> list[dict]:
    rows: list[dict] = []
    headings: list[str] = []
    category, in_run = "", False
    for page_no, words in enumerate(pages, start=1):
        labels = [w for w in words if w.text in LABELS]
        if not any(w.text == "Description" for w in words) or not labels:
            continue   # intro and key pages
        columns = {LABELS[w.text]: w.x0 for w in labels}
        top = max(w.y1 for w in labels)
        bottom = min((w.y0 for w in words if FOOTER.match(w.text)), default=float("inf"))
        for line in _lines([w for w in words if top < w.y0 < bottom]):
            if line[0].x0 > NAME_MAX_X:   # centred section heading
                text = " ".join(w.text for w in line)
                headings = (headings if in_run else []) + [text]
                # a "SEE ... LABEL FOR ALLERGENS" heading is a complete (empty) section: don't nest under it
                category, in_run = " - ".join(headings), NO_INFO not in text
                continue
            in_run = False
            row = {"Product_Name": " ".join(w.text for w in line if w.x0 < NAME_MAX_X),
                   "Category": category, "source_page": page_no}
            cells: dict[str, str] = {}
            for w in (w for w in line if w.x0 >= NAME_MAX_X):
                col, x = min(columns.items(), key=lambda c: abs(c[1] - w.x0))
                if abs(x - w.x0) > COLUMN_TOLERANCE:
                    raise ValueError(f"page {page_no}: {w.text!r} at x={w.x0:.0f} is under no allergen column")
                if col == "treeNutSource":
                    cells[col] = (cells.get(col, "") + " " + w.text).strip()
                elif w.text not in markers:
                    raise UnknownAllergen(f"page {page_no}, {row['Product_Name']}: unknown marker {w.text!r}")
                else:
                    cells[col] = markers[w.text]
            blank = "" if NO_INFO in category else markers[""]
            row |= {a: cells.get(a, blank if a in columns else "") for a in ALLERGENS}
            cereals = [row[c] for c in GRID_CEREALS]
            row["gluten"] = "Yes" if "Yes" in cereals else ("No" if set(cereals) == {"No"} else "")
            if "treeNutSource" in cells:
                row["treeNutSource"] = cells["treeNutSource"]
            rows.append(row)
    return rows


def parse(pdf: Path, source: dict) -> list[dict]:
    return parse_pages(page_words(pdf), source["markers"])
```

Replace `pipeline/parsers/__init__.py`:

```python
from pipeline.parsers import premier_inn_breakfast, whitbread_drinks_grid

# parser name (as used in config/chains.yaml) -> parse(pdf_path, source_config) -> rows
PARSERS = {
    "premier_inn_breakfast": premier_inn_breakfast.parse,
    "whitbread_drinks_grid": whitbread_drinks_grid.parse,
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_whitbread_drinks_grid.py -v` Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/parsers/__init__.py pipeline/parsers/whitbread_drinks_grid.py tests/test_whitbread_drinks_grid.py
git commit -m "feat: Whitbread drinks allergen grid parser"
```

---

### Task 7: `run` and `eval`, ground-truth config, golden rows, approval

**Files:**
- Create: `pipeline/evaluate.py`, `config/pearlscan_columns.yaml`, `config/ground_truth_errata.yaml`, and three golden files: `golden/beefeater_ss25_breakfast_menu_allergy_nutrition_v1.csv`, `golden/beefeater_ss25_drinks_menu_allergy_nutrition_v1.csv`, `golden/brewers_fayre_allergy_nutrition_ss25_drinks_menu.csv`
- Modify: `pipeline/cli.py` (replace the whole file)
- Test: `tests/test_evaluate.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes:
  - `load_columns` (Task 1).
  - `finalise` and `write_csv` (Task 3).
  - `load_chains`, `manifest_row`, `page_texts` and `text_sha` (Task 4).
  - `PARSERS` (Task 6).
- Produces:
  - In `pipeline.evaluate`:
    - `read_csv(path) -> list[dict]`.
    - `same(want, got) -> bool`.
    - `norm(text) -> str`.
    - `ground_truth_file(gt_dir, pdf_stem) -> Path | None`.
    - `compare_ground_truth(truth, ours, mapping, errata) -> dict`, with keys `rows, recall, cells, unmatched, mismatches, passed`.
    - `compare_golden(golden, ours) -> list[str]`.
  - In `pipeline.cli`:
    - `class SourceNotApproved(Exception)`.
    - `run(inputs, chains_file, outputs, only=None) -> dict[Path, list[dict]]`.
    - `evaluate(chains_file, outputs, ground_truth, golden, config) -> list[str]`.
  - CLI: `uv run python -m pipeline.cli manifest | run [--chain KEY] | eval`.

- [ ] **Step 1: Create the ground-truth config**

`config/pearlscan_columns.yaml`:

```yaml
# Pearl Scan (ground truth) column -> our column. Used only by `eval`, which checks nutrition and
# serving size. menu_section is not compared: sections follow our own naming rules.
item_name: Product_Name
servingsize: Serving_Size
servingsizeunit: Serving_Size_Unit
kj: energykJ_Per Portion
kcal: energykCal_Per Portion
fat: fat_Per Portion
satfat: saturates_Per Portion
carb: carbohydrates_Per Portion
sugar: sugars_Per Portion
fibre: fibre_Per Portion
protein: protein_Per Portion
salt: salt_Per Portion
sodium: sodium_Per Portion
caffeine: caffeine_Per Portion
vitaminC: vitaminC_Per Portion
vitaminB12: vitaminB12_Per Portion
kj_100: energykJ_Per 100g/ml
kcal_100: energykCal_Per 100g/ml
fat_100: fat_Per 100g/ml
satfat_100: saturates_Per 100g/ml
carb_100: carbohydrates_Per 100g/ml
sugar_100: sugars_Per 100g/ml
fibre_100: fibre_Per 100g/ml
protein_100: protein_Per 100g/ml
salt_100: salt_Per 100g/ml
sodium_100: sodium_Per 100g/ml
```

`config/ground_truth_errata.yaml`:

```yaml
# Known errors in the Pearl Scan ground truth, each confirmed by a person against the PDF.
# `eval` skips these cells. column: a Pearl Scan column name, or "*" for a whole row.
# - file: m19968-nutritional-info-ice-cream_v0.1.csv
#   item: Fairtrade Vanilla 1 Scoop Tub
#   column: kj
#   reason: Pearl Scan wrote 82; the PDF says ...
[]
```

- [ ] **Step 2: Create the golden files**

These rows came from the parser output. **A person must check every allergen cell against the rendered PDF** and fix any cell that's wrong before this task is committed. Don't correct these files from pipeline output; that would defeat the check.
- Breakfast: page 2 for the bakery items, page 4 for Marmite, page 6 for Kelloggs and Black Pudding.
- Drinks: find each item on pages 3–8 and confirm each `Y` is in the column shown.

`golden/beefeater_ss25_breakfast_menu_allergy_nutrition_v1.csv`:

```csv
Product_Name,Category,Serving_Size,Serving_Size_Unit,Diet,gluten,wheat,rye,barley,oats,spelt,kamut,celery,crustacean,egg,fish,lupin,milk,mollusc,mustard,peanut,sesame,soya,sulphite,treeNuts,treeNutSource
Croissant,PREMIER INN BREAKFAST - UNLIMITED CONTINENTAL - BAKERY (per item/slice),,,V,Yes,Yes,May contain,May contain,May contain,No,No,No,No,Yes,No,No,Yes,No,No,No,No,May contain,No,May contain,"may: Almond, Hazelnut"
Gluten Free Bread,PREMIER INN BREAKFAST - UNLIMITED CONTINENTAL - BAKERY (per item/slice),,,V,No,No,No,No,No,No,No,No,No,Yes,No,No,No,No,No,No,No,No,No,No,
Malted Brown Sandwich Bread (per slice),PREMIER INN BREAKFAST - UNLIMITED CONTINENTAL - BAKERY (per item/slice),,,VE,Yes,Yes,May contain,Yes,May contain,No,No,No,No,No,No,No,No,No,No,No,No,May contain,No,No,
Blueberry Muffin,PREMIER INN BREAKFAST - UNLIMITED CONTINENTAL - BAKERY (per item/slice),,,V,Yes,Yes,No,May contain,May contain,No,No,No,No,Yes,No,No,May contain,No,No,No,No,May contain,No,May contain,"may: Almond, Brazil, Cashew, Hazelnut, Macadamia, Pecan, Pistachio, Walnut"
Marmite Portions,"PREMIER INN BREAKFAST - UNLIMITED CONTINENTAL - PRESERVE, SPREADS AND JAM (per item)",,,VE,Yes,Yes,Yes,Yes,Yes,No,No,Yes,No,No,No,No,No,No,No,No,No,No,No,No,
Kelloggs Muesli Fruit,PREMIER INN BREAKFAST - UNLIMITED CONTINENTAL - YOGHURTS AND CEREALS,45,g,V,Yes,Yes,Yes,Yes,Yes,No,No,No,No,No,No,No,Yes,No,No,May contain,No,No,Yes,May contain,"may: Almond, Brazil, Cashew, Hazelnut, Macadamia, Pecan, Pistachio, Walnut"
Black Pudding (per slice),PREMIER INN BREAKFAST - UNLIMITED COOKED BREAKFAST (per item),,,,Yes,Yes,No,Yes,No,No,No,No,No,No,No,No,No,No,No,No,No,No,No,No,
```

`golden/beefeater_ss25_drinks_menu_allergy_nutrition_v1.csv`:

```csv
Product_Name,Category,gluten,wheat,rye,barley,oats,spelt,kamut,celery,crustacean,egg,fish,lupin,milk,mollusc,mustard,peanut,sesame,soya,sulphite,treeNuts
(SPRITZ) APEROL SPRITZ,SPRING SUMMER 2025 - COCKTAILS,No,No,No,No,No,,,No,No,No,No,No,No,No,No,No,No,No,Yes,No
(CLASSIC) MOJITO,SPRING SUMMER 2025 - COCKTAILS,No,No,No,No,No,,,No,No,No,No,No,No,No,No,No,No,No,No,No
TEQUILA ROSE,SHOTS,No,No,No,No,No,,,No,No,No,No,No,Yes,No,No,No,No,No,No,No
CARLING,DRAUGHT BEERS & CIDERS,Yes,Yes,No,Yes,No,,,No,No,No,No,No,No,No,No,No,No,No,No,No
ALPRO SOYA DRINK,HOT DRINKS - COFFEE / TEA,No,No,No,No,No,,,No,No,No,No,No,No,No,No,No,No,Yes,No,No
"JAM SHED, CHARDONNAY",WINES - WHITE,No,No,No,No,No,,,No,No,Yes,Yes,No,Yes,No,No,No,No,No,Yes,No
HENDRICK'S,SPIRITS - GIN,No,No,No,No,No,,,No,No,No,No,No,No,No,No,No,No,No,No,No
```

`golden/brewers_fayre_allergy_nutrition_ss25_drinks_menu.csv`:

```csv
Product_Name,Category,gluten,wheat,rye,barley,oats,spelt,kamut,celery,crustacean,egg,fish,lupin,milk,mollusc,mustard,peanut,sesame,soya,sulphite,treeNuts
APEROL SPRITZ,SPRING SUMMER 2025 - COCKTAILS,No,No,No,No,No,,,No,No,No,No,No,No,No,No,No,No,No,Yes,No
BAILEYS IRISH CREAM,LIQEUER & SPECIALITIES,No,No,No,No,No,,,No,No,No,No,No,Yes,No,No,No,No,No,No,No
CARLING,DRAUGHT BEERS & CIDERS,Yes,Yes,No,Yes,No,,,No,No,No,No,No,No,No,No,No,No,No,No,No
ALPRO SOYA DRINK,HOT DRINKS - COFFEE / TEA,No,No,No,No,No,,,No,No,No,No,No,No,No,No,No,No,Yes,No,No
JAM SHED CHARDONNAY,WINES - WHITE,No,No,No,No,No,,,No,No,Yes,Yes,No,Yes,No,No,No,No,No,Yes,No
BOMBAY SAPPHIRE LONDON DRY,SPIRITS - GIN,No,No,No,No,No,,,No,No,No,No,No,No,No,No,No,No,No,No,No
```

- [ ] **Step 3: Write the failing tests**

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
```

`tests/test_cli.py`:

```python
from pathlib import Path

import pytest

from pipeline.cli import SourceNotApproved, evaluate, run

ROOT = Path(__file__).resolve().parent.parent
CHAINS = ["16_Beefeater", "17_Brewersfayre", "21_TableTable"]


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
    assert sorted(p.stem for p in written) == CHAINS
    for path, rows in written.items():
        assert len(rows) == 59 + 148   # breakfast items + drinks items
        assert not [r for r in rows if r["flags"]]
        assert {r["region"] for r in rows} == {"UK"} and {r["method"] for r in rows} == {"parser"}
        assert len({r["source_file"] for r in rows}) == 2
    failures = evaluate(cf, tmp_path / "out", ROOT / "inputs" / "ground-truth", ROOT / "golden", ROOT / "config")
    assert failures == []


def test_run_refuses_unapproved_sources(tmp_path):
    with pytest.raises(SourceNotApproved):
        run(ROOT / "inputs", chains_file(tmp_path, approved=False), tmp_path / "out")
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest tests/test_evaluate.py tests/test_cli.py -v` Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.evaluate'`.

- [ ] **Step 5: Implement `pipeline/evaluate.py`**

```python
"""Compare our output with Pearl Scan ground truth (nutrition) and hand-verified golden rows (allergens)."""
import csv
import re
from pathlib import Path

ROW_RECALL_MIN = 0.99


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


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
            got = o.get(col)
            if got is None:
                failures.append(f"{g['Product_Name']}: column {col!r} not in output")
            elif not same(want, got):
                failures.append(f"{g['Product_Name']}.{col}: expected {want!r}, got {got!r}")
    return failures
```

- [ ] **Step 6: Replace `pipeline/cli.py` with the full version**

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
            cache_key = (text_sha(page_texts(pdf)), source["parser"], repr(sorted(source["markers"].items())))
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

- [ ] **Step 7: Run the full test suite**

Run: `uv run pytest -v` Expected: 56 passed. If `test_run_writes_one_csv_per_chain_and_passes_eval` fails on a golden cell, check that cell against the PDF. If the golden file is right, fix the parser; if it's wrong, fix the golden file after checking the PDF.

- [ ] **Step 8: Approval by a person**

Ask the person to:
1. Check the golden files (Step 2).
2. Check each source in `config/chains.yaml` against its PDF: that `markers` matches the PDF's key, and that `disclaimer` is word for word.
3. Set `approved: true` on all six sources.

Don't set `approved: true` yourself.

After approval, run:

- `uv run python -m pipeline.cli run`. Expected:

  ```
  outputs/16_Beefeater.csv: 207 rows, 0 with errors, 0 with warnings
  outputs/17_Brewersfayre.csv: 207 rows, 0 with errors, 0 with warnings
  outputs/21_TableTable.csv: 207 rows, 0 with errors, 0 with warnings
  ```

- `uv run python -m pipeline.cli eval`. Expected: a ground-truth line per breakfast PDF reading `ground truth 59 rows, recall 100.0%, 590 cells, 0 mismatches`, a golden line per golden file reading `0 failures`, then `eval: all checks passed`, with exit code 0.

- [ ] **Step 9: Commit**

```bash
git add pipeline/evaluate.py pipeline/cli.py config/pearlscan_columns.yaml config/ground_truth_errata.yaml config/chains.yaml golden tests/test_evaluate.py tests/test_cli.py
git commit -m "feat: run/eval commands, ground-truth check, first three chains"
```

---

## Later phases (separate plans, per spec §10)

- **Phase 2:** remaining digital table layouts, one parser and golden file per layout, with chains added to `config/chains.yaml`. Add the ratio check and basis synonyms when a layout first needs them.
- **Phase 3:** LLM routes.
  - `pipeline/extract.py` with the Anthropic Batch API backend.
  - Structured output from `build_row_model(...).model_json_schema(by_alias=True)`.
  - The model copies markers as printed, and code maps them.
  - A content-hash cache in `work/`.
  - Menu-layout PDFs first, then Papa John's (79 image-only pages), then repair.
- **Phase 4:** a review/overrides loop if flag volume justifies it.

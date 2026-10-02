# Complete the Pipeline: Remaining 12 Chains, LLM Routes, Finish Implementation Plan

**Status: approved by the user on 2026-10-02.** Before Slice 6 starts, a 5-page calibration run measures how much plan quota a call uses (see Task 6.10).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan slice by slice. Steps use checkbox (`- [ ]`) syntax for tracking. **Read "How this plan executes" before starting:** each slice gets its own code-level plan, written after prototyping, under this plan's approval.

**Goal:** Every PDF in `inputs/` produces a checked row in its chain's CSV (17 chains, 35 PDFs), or is listed as having no nutrition data, with allergen and nutrition values extracted exactly as printed and verified against Pearl Scan (nutrition) and hand-verified golden rows (allergens).

**Architecture:** What exists (Phases 1 to 2b, merged on `main`, 129 tests):
- Layout parsers (`premier_inn_breakfast`, `whitbread_drinks_grid`, `numeric_table`) driven by `config/chains.yaml`.
- A column dictionary, per-chain CSV export with `flags`, and `eval` against Pearl Scan ground truth.

What this plan adds:
- A config-driven **allergen matrix** parser (Cineworld, Pizza Hut, and the Whitbread drinks grid migrated onto it).
- Parsers for the remaining table layouts (Domino's, Odeon, Coffee #1, Starbucks).
- A **vision/LLM route** (headless Claude Code, `claude -p`) for the PDFs whose text layer is unusable (Vue, Papa John's, Krispy Kreme) and for menu layouts that need judgement about what a dish name is (Brewhouse, Cookhouse, Top Golf).
- Finishing work: a flags report, a coverage check, and docs.

**Tech Stack:** Python 3.12, `uv`, `pydantic` v2, `pyyaml`, `pdfplumber`, `pytest`, poppler. No new Python dependency: the LLM slices call the `claude` CLI (version 2.1.287 installed) as a subprocess.

**Spec:** [docs/pipeline-design.md](../../pipeline-design.md), draft v3. This plan implements §10 from Phase 2c to the end.

## What you approve

Approving this plan authorises, without further questions:
1. **The work in slices 0 to 9 below,** executed natively in this session, one slice after another.
2. **Headless Claude Code calls** (`claude -p`) for slices 7 to 9, using your existing Claude Code login. No API key and no new dependency. Every call is capped with `--max-budget-usd`, and each run has call and token caps (see Slice 6). The calls count against your Claude plan or account. If `claude` is not logged in, slices 7 to 9 pause and everything else continues. A direct API client can be added later behind the same interface, but only if you ask.
3. **Local merges to `main`** after each slice's review (no remote exists, nothing is pushed).

What stays with you, and never blocks the work:
- **Setting `approved: true`** on each chain in `config/chains.yaml`. Until you do, `run` skips the chain and `eval` skips it, so unapproved chains don't stop later slices.
- **Eyeballing golden rows.** I pre-verify every golden row by rendering the PDF page to an image and reading it, and I mark which rows I verified that way. You spot-check.

## How this plan executes

The earlier slices showed that a layout's real shape only appears when you run a prototype against Pearl Scan: header blocks, touching cells, wrapped names and soft hyphens were all found that way, and each changed the design. So the code for a slice cannot be written correctly in advance. Each slice therefore runs this loop, and the loop is part of the plan:

1. **Survey and prototype** the layout against its ground truth in a scratch copy, until row recall and cell agreement are 100% apart from confirmed Pearl Scan errors.
2. **Write the slice's code plan** (tasks, tests, full code) to `docs/superpowers/plans/`, generated from the tested scratch files, and **dry-run it** task by task from a clean checkout. This is how Phases 2a and 2b were done.
3. **Execute it natively,** test first, committing per task.
4. **Fresh Opus review** of the whole slice branch, one fix pass with a failing test per Critical or Important finding, minors recorded.
5. **Merge locally to `main`,** re-run the suite on the merged tree, delete the branch.

A slice is **done** when: its tests and the full suite pass, `eval` passes for its chains, every PDF in the slice is assigned in `config/chains.yaml` with `approved: false`, and the design doc and README are current.

Disagreements between our output and Pearl Scan are triaged by rendering the page and reading it: where Pearl Scan is wrong, it goes into `config/ground_truth_errata.yaml` with the reason; where we are wrong, we fix the parser. Pearl Scan is known to contain errors (Vue, Odeon typos, a mojibake name).

## Global Constraints

- Git holds code, `schemas/`, `config/` and `golden/` only. Data (`inputs/`, `outputs/`, `samples/`, `work/`) is gitignored. **Never delete or overwrite data directories when testing; use temp dirs.**
- **Extract, don't transform.** Values as printed, no unit or basis conversion, nothing derived. Names as printed minus layout artifacts; reviewer comments in `PDF_list_June25_check.xlsx` take precedence.
- Allergen cells are `Yes` / `May contain` / `No` / blank. `No` only when the PDF's key declares absence; blank means not stated. Each source's marker key lives in config; an unknown marker stops the run.
- Anything a parser can't place raises. Nothing is guessed or dropped. LLM output is validated by the same Pydantic row model, and the model **copies markers as printed**: code maps them.
- `flags` hold problems and values are never changed. Flags can come from the source.
- `run` and `eval` skip unapproved chains. Only a person sets `approved: true`.
- No new dependencies planned. LLM calls go through the `claude` CLI; a direct API client (`anthropic`) is out of scope unless you ask for it.
- Tests that read PDFs must stay under ~60 s for the whole suite; cache parsed PDFs in fixtures where a test file parses the same PDF repeatedly.

## Review Focus

1. **A blank allergen cell read as "No".** A matrix without a "no mark means absent" statement must leave unmarked cells blank. Every matrix slice needs a test with a PDF whose key doesn't say so, and a golden row.
2. **Ground-truth lookup misses.** The Domino's pizza file has a soft hyphen in its name and is silently skipped today (1,422 rows never evaluated). Every PDF must be evaluated or listed as having no ground truth.
3. **Variants and repeated names** (sizes, milk types, crusts, regions). Rows must not collide or merge; duplicates with different values are flagged.
4. **The LLM changing a number or inventing a row.** Validators and the Pearl Scan comparison are the only defence: row coverage per page must equal what the page shows; a mismatch reaches a person.
5. **Runaway spend.** A per-call `--max-budget-usd`, a per-run cap on calls and reported cost, results cached by content hash, and a dry-run that prints the estimate. Each call carries ~20k tokens of Claude Code overhead, so batching several pages per call must be tested for accuracy before it is used.
6. **Slanted or rotated text** (Coffee #1 beverages, some matrix headers). `page_words_fine` refuses it; the affected slice needs a documented alternative, never a guess.

---

## Slices

The order puts everything that needs no API key first.

| # | Slice | Chains / PDFs | Route |
|---|---|---|---|
| 0 | Foundations | all | tooling |
| 1 | Allergen matrix parser | Cineworld (46), Pizza Hut (8), Whitbread drinks migrated | parser |
| 2 | Domino's | Domino's (6): sides, pizzas | parser |
| 3 | Odeon | Odeon (59): 3 nutrition PDFs, 3 pre-packed matrices | parser |
| 4 | Coffee #1 | Coffee #1 (47): food, beverages | parser |
| 5 | Starbucks | Starbucks (7): food, beverages | parser |
| 6 | LLM backend (`claude -p`) | none (infrastructure) | LLM |
| 7 | Vision chains | Vue (58), Papa John's (26), Krispy Kreme (35) | vision |
| 8 | Menu layouts | Brewhouse (45), Cookhouse (49), Top Golf (73) | LLM text or vision |
| 9 | Finish | all | tooling, docs |

Starting position: 5 of 17 chains done (Beefeater, Brewers Fayre, Table Table, Five Guys, Pizza Express): 9 of the 35 PDFs, 26 to go.

### Slice 0: Foundations

Fixes found while surveying that would otherwise hide failures in later slices.

**Tasks**
- [ ] **0.1 Ground-truth lookup is robust to odd file names.** `ground_truth_file` must match stems after Unicode normalisation (NFKC, strip soft hyphens U+00AD and zero-width characters, collapse `%20` and `_20`). Tests: the Domino's pizza file is found; `Previous/` is still ignored; `_v0.1` still beats the original.
- [ ] **0.2 `eval` says what it skipped.** For every approved source with neither ground truth nor golden rows, print `<chain> <pdf>: not evaluated`. A new `--strict` flag makes that a failure; the final slice turns it on for the whole repo.
- [ ] **0.3 `page_words_fine` is fast.** Bucket fine words by line instead of scanning all of them per numeric word. Target: SUM25 beverage (73 pages) under 2 s, `nutrition_pizzas` (18 pages, ~11k words per page) under 10 s. Output must be identical on the existing PDFs (a test compares token multisets before and after).
- [ ] **0.4 Pearl Scan column map covers every ground-truth column.** `config/pearlscan_columns.yaml` gets the missing names (`serves`, `slice/portion/piece`, `kcal_pizza`, `*_slice`, `*_product_as_sold`, `num_of_slices`, `total_slices`, vitamins, `caffeine`), each mapped to a dictionary column or marked as not compared. A test fails if a ground-truth file has a column that is in neither list.
- [ ] **0.5 Dictionary additions** needed by later slices (`Serves`, count columns such as `total_slices`/`num_of_portions`, `Suitable for` columns), each added to `schemas/columns.yaml` with a test.

**Acceptance:** suite green; `eval` output unchanged for the 5 existing chains plus a `Dominos` line saying `nutrition_pizzas: ground truth found (1,422 rows)` (not evaluated yet because no source exists).

### Slice 1: Allergen matrix parser (Cineworld, Pizza Hut)

**Design facts (from the survey):**
- *Cineworld* (12 pp): sections of items with an energy (kcal) column and one column per allergen; cells hold `✓` (contains) or `▲` (may contain), 272 and 187 of them; the key page defines both. Ground truth is kcal only (226 rows), with names like `Sweet Popcorn - Large` (size in the name; we use `Size` and `Serving_Size`).
- *Pizza Hut* (24 pp, 483 rows): `●` contains, `○` supply-chain risk (394 and 243); also "Suitable for" columns (vegetarian, vegan, coeliac) and nutrition columns. Reviewer rule: **the pizza name goes in `item_name`**. Ground truth has `servingsize`/unit, `num_of_slices`, kcal and macros per portion, and `_100` columns.
- *Whitbread drinks* already is this layout with `Y` marks; migrating it removes the bespoke parser.

**Tasks**
- [ ] **1.1 `allergen_matrix` parser** (`pipeline/parsers/allergen_matrix.py`): header labels (possibly rotated or multi-line) are mapped to dictionary columns by a `labels:` mapping in config; marker cells map through `markers:`; nutrition cells to the left of the allergen block are read as numeric columns by position (reusing `numeric_table`'s column logic where possible). Unknown label, unknown marker, a mark under no column, and a row with no name all raise.
- [ ] **1.2 Migrate `whitbread_drinks_grid`** onto `allergen_matrix` with identical output; its existing tests and golden files must pass unchanged, then the old parser is deleted.
- [ ] **1.3 Cineworld chain** `46_Cineworld`: parser config, golden rows (including a `▲` row and an item with no marks), `Size`/`Serving_Size` split, ground-truth match on all 226 rows.
- [ ] **1.4 Pizza Hut chain** `8_Pizzahut`: same, plus the pizza-name-in-`item_name` rule, suitable-for columns, and ground-truth match on all 483 rows.
- [ ] **1.5 Docs:** README and design doc updated (matrix parser, marker keys for the three chains).

**Acceptance:** `eval` passes for the three chains; golden files exist for each PDF; a test shows a matrix whose key does not declare absence leaves unmarked cells blank.

### Slice 2: Domino's

**Design facts:** `nutrition_sides-and-desserts` (3 pp, 82 GT rows) has per-100g (10 values), `Serves`, per-product-as-sold (10), a **text** portion cell (`Portion`, `Dip`, `Piece`), then per-portion (10): numeric rows with a non-numeric cell in the middle. `nutrition_pizzas` (18 pp, 1,422 GT rows) has pizza name and crust only on the first row of a group, with size rows beneath (`Large`, `Medium`, `Small`, `Personal`), per-100g, per-pizza and per-slice blocks. Reviewer rules: first per-portion set is `_pizza` (pizzas) / `_product_as_sold` (sides), second is `_slice` / left as is; new per-portion columns added.

**Tasks**
- [ ] **2.1 `numeric_table` supports text cells inside a row** (a `text_columns:` config naming cells that hold words), with the same fail-loud rules.
- [ ] **2.2 Group rows** (a name or crust printed once, repeated down the group) via a `carry:` option that names which leading cells carry down; a size cell becomes `Size`.
- [ ] **2.3 Sides chain** and **2.4 pizzas chain** under `6_Dominos`; the pizzas PDF gets ground truth now that Slice 0 finds it. Dictionary bases `Per Pizza`, `Per Slice`, `Per Product As Sold` already exist.

**Acceptance:** `eval` passes for both PDFs against 82 and 1,422 rows; no row collisions across crusts and sizes.

### Slice 3: Odeon

**Design facts:** three regions (UK `v88`, Belfast and ROI `v87`) of two PDFs each: a nutrition table (`Energy(KJ)`, kcal, fat, saturates, carbohydrate, sugars, protein, sodium, salt, fibre, with serving size and unit such as `oz`, `ml`, and words like `Negligible`) and a pre-packed product matrix (ingredients with allergens in bold, serving size, energy, storage text). Ground truth: UK 714 and 106 rows, Belfast 149 and 90, ROI 149 and 90. Reviewer: Odeon UK typos (`rasoberry`, `nealigible`) were Pearl Scan's, not the PDF's. Belfast and ROI PDFs have identical text.

**Tasks**
- [ ] **3.1 Nutrition tables** through `numeric_table` (serving size/unit as `text_columns`), three regions as three sources.
- [ ] **3.2 Pre-packed matrices:** survey the layout (ingredient paragraphs with bold allergens); extract nutrition columns by position and the ingredients text into `Ingredients`. Allergens in bold are **not** derived from the ingredients unless the PDF has an allergen column; if it has none, the allergen columns stay absent.
- [ ] **3.3 Regions:** `region: UK|NI|ROI` per source; identical Belfast and ROI text is parsed once (existing cache key).

**Acceptance:** all six PDFs match their ground truth; `Negligible` and similar words are kept as printed.

### Slice 4: Coffee #1

**Design facts:** *Food* (18 pp, 92 GT rows): one block per product with ingredient paragraph (allergens in capitals, `*` contains, `P` cross-contamination risk at the manufacturing site) and a **vertical** nutrition list (`KJ`, `Kcal`, `Fat`, `Sat`, `Carbs`, `Sugar`, `Fibre`, `Protein`, `Salt`) with per-100g and per-portion columns. *Beverages* (28 pp, 371 GT rows): per 100 ml and per product by size (`Regular`, `Large`), plus an `ALLERGENS` column; **slanted text** defeats `page_words_fine` (a documented probe in the Phase 2b review). Reviewer: vitamins added for some drinks.

**Tasks**
- [ ] **4.1 Food parser** (block parser: product name, ingredient text, vertical nutrition columns by position). `*` and `P` map through the marker key; ingredient text goes to `Ingredients` unchanged.
- [ ] **4.2 Beverage parser.** First try poppler words (`page_words`); the slanted pages may need a rotation-aware path. If neither yields exact cells, the PDF routes to vision in Slice 7 and this task records why. Either way the ground-truth gate applies.
- [ ] **4.3 Chain `47_Coffee1`** with both PDFs, golden rows for `*` and `P` items.

**Acceptance:** both PDFs match ground truth, by parser or by the vision route.

### Slice 5: Starbucks

**Design facts:** *Food* (20 pp, 93 GT rows): per product, a multi-line ingredient paragraph with allergens in capitals, a name, `Suitable for Vegetarian/Vegan` as `Y`/`N`, and nutrition per portion; names and ingredients interleave across lines. *Beverages* (73 pp, 1,464 GT rows): product names wrap over several lines; per size (`Short`, `Tall`, `Grande`, `Venti`) rows with energy, macros and caffeine; the milk type is part of the product line (`... - skimmed milk`). Pearl Scan builds `Product - milk - Size`; we use the dictionary's `Milk` and `Size` columns. A `Modifiers` section is cleaned of `kcal` (reviewer).

**Tasks**
- [ ] **5.1 Food parser**, **5.2 Beverage parser** (wrapped names, size rows, milk), **5.3 Chain `7_Starbucks`** with both PDFs.
- [ ] **5.4 Allergen summary column:** if the PDF prints an allergen summary column, map it through a marker key; ingredient capitals are never used to derive allergens.

**Acceptance:** 93 and 1,464 ground-truth rows match; each size and milk variant is its own row without collisions.

### Slice 6: LLM backend (headless Claude Code)

**Evidence (a trial on 2026-10-02):** one real call read the Vue ice-cream page image (the page whose text layer is corrupt) and returned the first four rows through `--json-schema`; every cell matched the page and Pearl Scan exactly, including `trace`, `08`, `05`, `09`. It took 11 s and reported $0.10, of which about 22k tokens were Claude Code's own system prompt and tool definitions.

**Design:** one function, `extract(page, columns, instructions) -> list[dict]`, behind a small interface. The first implementation shells out to:

```
claude -p --model claude-sonnet-5-5 --tools Read --add-dir work/pages \
       --json-schema <schema from build_row_model(columns)> --output-format json \
       --no-session-persistence --max-budget-usd <cap> "<instructions + image path>"
```

The image is a PNG the `Read` tool opens; a text page goes in the prompt. The result is read from `structured_output`; `usage` and `total_cost_usd` are recorded. The model is pinned by its full ID, never an alias, and is part of the cache key.

**Tasks**
- [ ] **6.1 Backend interface and `claude -p` implementation** (`pipeline/llm.py`): subprocess with an explicit timeout, `stdin` closed, no secrets passed or logged, errors (non-zero exit, `is_error`, schema mismatch) raised with the page and the stderr tail.
- [ ] **6.2 Content-hash cache** in `work/llm/` keyed on `sha256(page text or image) + columns.version + prompt version + model`; a re-run over unchanged inputs makes no calls (tested with a fake runner).
- [ ] **6.3 Budget guard:** per call `--max-budget-usd`; per run a cap on calls and on summed `total_cost_usd` (defaults: 400 calls, $60, configurable); the estimate is printed before the first call; exceeding a cap stops the run. `--dry-run` prints the estimate and calls nothing.
- [ ] **6.4 Overhead measurement:** compare a default call with `--bare` and with trimmed tools on the same page; keep whichever is cheapest **without** changing a single cell. Test a two-page call against two one-page calls for accuracy before ever batching pages.
- [ ] **6.5 Page rendering:** `pdftoppm -r 150`, long edge capped at 1568 px, into `work/pages/`.
- [ ] **6.6 Validation and repair:** every returned row goes through the same Pydantic model and arithmetic checks; rows that fail get **one** re-read of that page with the failure reasons in the prompt; still-failing rows are kept with `flags` (never dropped, never altered).
- [ ] **6.7 Coverage check:** a page's row count is compared with an independent count (text tokens where the text layer is usable, otherwise a second pass); a shortfall is flagged.
- [ ] **6.8 Bounded concurrency:** at most 3 calls in flight, with back-off on rate-limit errors.
- [ ] **6.10 Quota-aware runs:** a rate-limit or quota error pauses the run with a clear message (never fails the whole job); every finished page is already cached, so the next run resumes where it stopped; runs go one PDF at a time so a stop leaves complete PDFs and at most one partial. Calibration first: 5 Vue pages through the real backend, the plan-quota change noted by the user, then the full run is sized from it.
- [ ] **6.9 Tests without the CLI:** a fake runner returning canned `claude -p` JSON; tests for cache hits, budget stop, a schema mismatch, a repair, marker copying (the model returns `▲`, code maps it), a timeout, and an `is_error` result.

**Acceptance:** all tests pass with the fake runner; one real page round-trips and its cost and duration are printed; nothing secret appears in `work/` or logs.

### Slice 7: Vision chains

**Design facts:** *Vue* (14 pp, 3 PDFs): the embedded font drops characters (`197` extracts as `19`), so the page image is the only reliable source; nutrition only, no allergens; sections like `ICE CREAM SCOOPED PRODUCTS` with `cont.` suffixes to strip (reviewer); text cells such as `trace`; blank cells. *Papa John's* (79 pp, image-only): per-100g and per-portion with weight, slices, portions; reviewer: `recommended_portions` spelling, `chicken poppers`, a date-shaped value. *Krispy Kreme* "Minions" (61 pp): icon-font allergens, nutrition per 100g and portion, three-part layout (suitable-for, allergens, nutrition).

**Tasks**
- [ ] **7.1 Vue** (3 PDFs, `58_Vue`), **7.2 Papa John's** (`26_PapaJohns`), **7.3 Krispy Kreme** (`35_KrispyKreme`): config with the page ranges and instructions, ground-truth gate, golden rows for allergens (Krispy Kreme).
- [ ] **7.4 Pearl Scan errors found along the way** (Vue's `82` kJ next to `197` kcal, `08` salt) go into the errata file with page evidence.

**Acceptance:** each PDF's rows and cells match ground truth apart from confirmed errata; cost and cache stats are printed; a second run makes zero API calls.

### Slice 8: Menu layouts

**Design facts:** Brewhouse (4 one-page menus, 126 GT rows), Cookhouse (2 PDFs, 205 rows; the text layer is partly garbled) and Top Golf (12 pp, 118 rows). A dish is `Name, description… V L (589kcal) 5.50`: multi-column pages, the name is the text before the first comma, dietary tags are inline, prices are present. Only kcal is in the ground truth. Reviewer: Cookhouse add-ons must not carry the main meal's name; Brewhouse `#NAME?` rows came from Excel.

**Tasks**
- [ ] **8.1 Text route** (`extract` on layout text) for Brewhouse and Top Golf; **8.2 vision route** for Cookhouse where the text is garbled. Dietary tags go to `Diet` as printed; prices are not extracted (not in the dictionary).
- [ ] **8.3 Chains** `45_Brewhouse`, `49_CookhousePub`, `73_TopGolf`; the Cookhouse add-on naming rule as a config instruction with a test row.

**Acceptance:** ground-truth match on all rows; add-ons and sections follow the reviewer rules.

### Slice 9: Finish

**Tasks**
- [ ] **9.1 Flags report:** `python -m pipeline.cli flags` writes `outputs/_flags.csv` listing every flagged row with chain, source file, page, flag and value, so a person can review source inconsistencies in one place.
- [ ] **9.2 Coverage test:** every PDF in `inputs/` is assigned to a source in `config/chains.yaml`, and `eval --strict` is clean (no approved source is left unevaluated).
- [ ] **9.3 Docs:** design doc status, §2 table, §10 marked complete; README status table; remove stale text.
- [ ] **9.4 Final whole-repo review** by a fresh Opus reviewer, with the review's Critical and Important findings fixed.

**Acceptance:** 17 of 17 chains configured; `eval --strict` exits 0 with every chain approved; the suite is green; the docs describe the final state.

---

## Cost and risk

- **Calls (Slices 6 to 8):** about 154 vision pages (Vue 14, Papa John's 79, Krispy Kreme 61) plus about 26 menu pages, so roughly 180 calls for a full run if each page is its own call. At the trial's $0.10 per call that is about $18 per full run on a per-token account (the trial's overhead dominates, and Task 6.4 tries to cut it); on a subscription it counts against your plan limits instead. Assume 3 to 5 development runs. Re-runs are free because of the cache. The caps in Task 6.3 stop a run before it can exceed 400 calls or $60.
- **Terms:** a subscription is meant for individual, interactive use. Running a recurring or production pipeline on `claude -p` may be outside what your plan allows; check Anthropic's terms before relying on it beyond this one-off extraction. That is your call; the backend interface keeps an API client possible.
- **Biggest technical risks:** Starbucks' interleaved name/ingredient layout (Slice 5), Coffee #1's slanted beverages (Slice 4, with a vision fallback), and Pearl Scan errors that look like parser errors (mitigated by reading the page image for each disagreement).
- **If a slice can't reach the gate** (a layout no parser or prompt handles exactly), it stops, records what was tried and the closest result, and the plan continues with the next slice rather than loosening the gate.

## Order of work, once approved

Slice 0, then 1 to 5 (parsers, no LLM), then 6 to 8 (needs a logged-in `claude`), then 9. After each slice I report what merged, its test count and `eval` result, and carry on.

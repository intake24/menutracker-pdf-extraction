# Menu PDF → Nutrition & Allergen CSV: Pipeline Design

Status: draft v3 · 2026-10-01 (design-review decisions in §12; Phase 2 survey findings in §2 and §10)

## 1. Goal

Menu Tracker scrapes allergen and nutrition PDFs published by UK food chains. Today a paid human service, Pearl Scan, turns those PDFs into CSVs. This project replaces that service with an automated pipeline: deterministic parsers where a layout allows it, and an LLM where it doesn't.

The output is **one CSV per chain**, `outputs/<id>_<Key>.csv` (e.g. `16_Beefeater.csv`), using Menu Tracker's chain keys from `menutracker.ipynb`.
- Each row is one food, drink or product.
- Columns cover category, description, serving size, nutrients, allergens, and provenance.
- The output must be accurate enough to publish. Allergen data is safety-relevant.
- Re-running over new seasonal PDFs should cost almost nothing.

Principles, agreed in the design review:
- **Extract, don't transform.** Values are recorded exactly as the PDF prints them. Units and bases are never converted, and nothing is derived to fill a column. Text values such as `Negligible`, `Trace` and `<0.1` stay as printed.
- **Fail loudly.** Wording, markers or bases that aren't in the config stop the run with an error. They are never guessed at or dropped.
- **Pearl Scan is a reference, not the format.** Its human-curated CSVs, in `inputs/ground-truth/`, are used to check our nutrition values. Its reviewer comments guide our cleanup rules. The output format follows this document.

## 2. What the inputs look like (surveyed 2026-09-30)

| Kind | Files | Pages | Route |
|---|---|---|---|
| Digital, tabular (matrix/booklet/grid) | 27 | ~390 | Deterministic parser |
| Digital, menu layout (kcal next to dish names) | 7 (`04.25-BK-*`, `33496-*`, `33545-*`, `cookhouse_*`, `watford_*`) | ~25 | LLM on extracted text |
| Image-only (PowerPoint export, text as images) | 1 (`nutritional-information.pdf`, Papa John's, 79 pp) | 79 | LLM vision |

- **Scale.** 35 PDFs covering 17 chains, ~500 pages, ~1.7M characters of embedded text.
- **Multiple PDFs per chain.** A chain often has several PDFs (food, drinks, regional versions). One PDF can also serve several chains: the Premier Inn breakfast guide is published under Beefeater, Brewers Fayre and Table Table.
- **Regional versions.** Odeon has UK, Belfast (NI) and ROI versions. Pizza Express publishes `PEX-…` (England, Wales & Scotland) and `BEL-…` (Northern Ireland).
- **Allergen markers vary by chain.**

  | Chain | Markers |
  |---|---|
  | Cineworld | `✓` and `▲` (may contain) |
  | Coffee #1 | `●`, plus `P` for cross-contamination risk |
  | Pizza Hut | `●` and `○` |
  | Starbucks | `Y` / `N` |
  | Whitbread drinks | `Y` |
  | Krispy Kreme, Vue | Icon-font glyphs that extract as unreadable characters |
  | Cookhouse | `*`, `**` and `§` footnotes, and some garbled font encodings |

- **Text in nutrient cells.** `Negligible`, `trace`, `Traces`, `Tr`, `<0.1`, and stray `.` printing glitches.
- **Grids are the biggest files.** The grid-style `SUM25_…_CORE_BEVERAGE` (390k chars) and `nutrition_pizzas` (268k chars) are the most expensive and least reliable to send to an LLM, and the easiest to parse in code.

### Text-layer reliability (surveyed 2026-10-01)

For each PDF, the share of Pearl Scan's numeric cells that appear as tokens in the PDF's text layer. Cells that Pearl Scan rewrote (`5.0` → `5`) count against it, so ~80–90% is not by itself a problem. Single-digit shares are.

| Text layer | PDFs | What to do |
|---|---|---|
| ~100% | Starbucks (2), Coffee #1 beverages, Pizza Hut, Pizza Express (2), Five Guys, Odeon pre-packed matrices (3), Top Golf, Cineworld, Cookhouse kids, Brewhouse menus (4) | Parsers (Phase 2), or LLM text for menu layouts (Phase 3) |
| Visibly corrupt | **Vue (3 PDFs).** The embedded font drops characters: `197` extracts as `19`, `17` as `1`, `7.7` as `.`. The page image and Pearl Scan agree; the text does not. | **Vision only** (Phase 3). A text parser would write wrong numbers without any warning. |
| ~0% | Papa John's (0%, image-only), Krispy Kreme "Minions" (2.7%, icon font) | Vision (Phase 3) |

Two further findings:
- **12 of the Pearl Scan CSVs are Windows-1252, not UTF-8** (Excel exports). Readers must fall back to cp1252.
- **Some tables print neighbouring cells almost touching.** In the Pizza Express PDFs `1232` and `11.1` are 0.8 pt apart, and poppler returns them as one word, `123211.1`. Word-level extraction can't split these; character-level extraction can.

## 3. Architecture

```
                 config/chains.yaml  (chain key → sources: pdf, parser, region, markers, approved)
                          │
 inputs/*.pdf ──▶ 1. Ingest ── text hash, pages, image-only pages → work/manifest.csv
                          │
            ┌─────────────┼──────────────┐
            ▼             ▼              ▼
     2a Parser      2b LLM text    2c LLM vision       every route emits rows in the column
     (per layout)   (layout text)  (page PNG)          dictionary's names, values as printed
            └─────────────┼──────────────┘
                          ▼
                 3. Merge per chain ── + region, source_file, method
                          ▼
                 4. Validate ── dictionary types, arithmetic checks, duplicates → flags
                          ▼
                 5. Repair (LLM routes only) ── failed rows → one vision re-read
                          ▼
                 outputs/<id>_<Key>.csv
                          ▼
                 6. Evaluate ── nutrition vs Pearl Scan ground truth, allergens vs golden rows
```

### Stage details

**1. Ingest.**
- `pdftotext -layout` gives text per page, and `pdftotext -bbox` gives words with coordinates.
- Records page count, a text hash, and pages with fewer than 200 non-space characters (treated as image-only).
- PDFs with identical text, parsed by the same parser with the same markers, are parsed once and the result is reused (e.g. Brewers Fayre and Table Table drinks).

**2a. Deterministic parser** (`pipeline/parsers/<layout>.py`).
- One parser per **layout**, not per chain. `config/chains.yaml` says which layout each PDF uses.
- Signature: `parse(pdf_path, source_config) -> list[dict]`.
- About 50–150 lines each. Written once by a coding agent, then costs no tokens to run.

**2b. LLM on text.**
- Input: one page of `pdftotext -layout` text, with the column dictionary as a JSON Schema for structured output.
- The model **copies markers and values as printed**. Code maps markers through the source's `markers` key.
- The fixed prompt prefix is cached, and calls go through the Batch API.

**2c. LLM vision.**
- Page PNGs from `pdftoppm -r 150`, long edge ≤ 1568 px.
- Same output contract as 2b.
- Used only for image-only pages, icon-font glyphs that don't decode, and repairs.

**3. Merge per chain.** All of a chain's sources are concatenated into one row list. Each row gets `region`, `source_file` and `method`. Rows are never merged across regions or sources.

**4. Validate.**
- A Pydantic model built from `schemas/columns.yaml` checks every row:
  - Only dictionary columns are allowed.
  - Nutrient cells must be a number, `<number`, or an approved word.
  - Allergen cells must be `Yes`, `May contain` or `No`.
- Arithmetic checks run only on cells that are plain numbers:

  | Check | Rule | Severity |
  |---|---|---|
  | kJ ↔ kcal | `abs(kJ − 4.184·kcal) ≤ max(3%, 5 kJ)` | error |
  | Subsets | `saturates ≤ fat`, `sugars ≤ carbs` (+0.05) | error |
  | Atwater | `kcal ≈ 4P + 4C + 9F + 2·fibre`, within max(15%, 10 kcal) | warn |
  | Duplicates | same (name, category, size, milk, region) twice with different values | error |
  | Coverage | parser-specific: every item block in the PDF yields a row | error |

- Problems go into the `flags` column. Values are **never changed**, even when invalid, so a reviewer sees what the source said.

**5. Repair.** For the LLM routes only. Flagged rows are grouped by page and get one vision re-read. Anything still flagged goes to a person.

**6. Evaluate.** See §9.

## 4. Output format and column dictionary

`schemas/columns.yaml` is the single column dictionary for every chain. Its order is the column order.
- **Text:** `Product_Name, Product_Description, Size, Milk, CoffeeType, Ingredients, Category, Serving_Size, Serving_Size_Unit, Diet, notes`. The first six are Costa's columns.
- **Nutrients:** `<nutrient>_<basis>`.
  - Nutrients, in Costa's names: `carbohydrates, energykCal, energykJ, fat, fibre, protein, salt, saturates, sugars, vitaminB6, vitaminB12, vitaminC, zinc, sodium, caffeine`.
  - Bases: `Per 100g/ml, Per Portion, Per Pizza, Per Slice, Per Product As Sold`.
- **Allergens:** `gluten, wheat, rye, barley, oats, spelt, kamut, celery, crustacean, egg, fish, lupin, milk, mollusc, mustard, peanut, sesame, soya, sulphite, treeNuts`, then `treeNutSource`.
- **Provenance:** `region, source_file, source_page, method, flags`.

A chain's CSV contains only the dictionary columns that have a value for that chain. New columns are added to the dictionary first, and a parser emitting an unknown column is flagged.

### Value rules

| Topic | Rule |
|---|---|
| Nutrient values | Exactly as printed: a number, `<number`, or a dictionary word (`Negligible`, `Trace`, `Traces`, `Tr`). Anything else, e.g. a stray `.`, is flagged. |
| Basis names | Different wording for the same basis maps to one dictionary basis ("Per Serving" → `Per Portion`). That's renaming only; values are untouched. A basis not in the dictionary stops the run. |
| Allergen values | `Yes` (contains), `May contain` (traces or cross-contamination), `No` (**the PDF declares** it absent), blank (the PDF doesn't say). |
| Spelt / kamut | Blank unless the PDF names them separately. Guides that fold them into "Wheat" never declare them absent. |
| Allergen markers | Each source's `markers` key maps printed markers to the vocabulary, e.g. `{"✓": "Yes", "▲": "May contain"}`. `""` is what "no marker" means for that PDF. Unknown markers stop the run. |
| Menu-wide disclaimers | E.g. "Some dishes may contain traces of nuts". Stored once per source in `chains.yaml`. **Not** in the CSV, and never copied onto rows as `May contain`. |
| Item-level footnotes | `*may contain nuts` maps through the key to that allergen. Non-allergen notes (bones, alcohol) go into `notes` exactly as printed. |
| Names | Reviewer comments in `PDF_list_June25_check.xlsx` come first (e.g. Vue: remove `cont.`; Pizza Hut: pizza name in `item_name`). Otherwise names are as printed, minus layout artifacts: diet markers move to `Diet`, footnote marks move to `notes`, wrapped lines are rejoined. Typos in the source are kept; extraction must add none. |
| Sizes | An amount with a unit (`(per 45g)`, a weight column) goes into `Serving_Size` + `Serving_Size_Unit` and is removed from the name. Named sizes (`Small`, `Large`, `1 Scoop`) go into `Size`. Descriptive portions (`(per slice)`) stay in the name. Section bases (`MILK (per 100ml)`) stay in `Category`. |
| Category | The section heading path as printed, joined with ` - `. A menu title that applies to every section (e.g. `PREMIER INN BREAKFAST`) prefixes every section. A page title above a table (e.g. Pizza Express's `Breakfast (selected restaurants only)`) is a parent that persists until the next title: `parent - section`. Allowed titles are listed per source under `titles`; any other text above a table header stops the run. Where a table has a column-header block, the section name is the block's text left of the numeric columns. |
| Region | `UK`, `NI` or `ROI`, set per source. |

## 5. Configuration (`config/`)

`config/chains.yaml` has one entry per chain, keyed by Menu Tracker's script key. It replaces per-family schema files:

```yaml
16_Beefeater:
  chain: Beefeater
  sources:
    - pdf: beefeater_ss25_drinks_menu_allergy_nutrition_v1.pdf
      parser: whitbread_drinks_grid        # layout parser
      region: UK
      category: drinks                     # optional
      markers: {"Y": "Yes", "": "No"}      # from the PDF's key; "" = no marker
      disclaimer: >-                       # menu-wide statement, exactly as printed
        Our allergen information sheet does not include any “may contains” information ...
      approved: true                       # set by a person after checking against the PDF
```

- **Approval.** `run` refuses any chain with an unapproved source. A person checks `markers` and `disclaimer` against the PDF before approving.
- **Other config files:**
  - `config/pearlscan_columns.yaml` maps Pearl Scan's column names (`kj`, `satfat`, `kcal_100`, …) to ours. Used only by `eval`.
  - `config/ground_truth_errata.yaml` lists known Pearl Scan errors, each confirmed against the PDF.

## 6. Tools and language

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.12, `uv` | Both already installed; the PDF tooling is best in Python |
| Text, coordinates, render | poppler: `pdftotext -layout`, `pdftotext -bbox`, `pdftoppm`, `pdfinfo` | Already installed; `-bbox` gives word coordinates for grids with no new dependency. Five Guys needs nothing more. |
| Character-level cells | `pdfplumber` | Approved 2026-10-01. Splits cells that are printed almost touching (Pizza Express, §2). `numeric_table` takes its words from it for every table PDF; poppler's `-bbox` stays for the grid parsers. |
| Row model + JSON Schema | `pydantic` v2 | One definition drives both extraction and validation |
| Config | `pyyaml` | Human-edited, version-controlled config |
| LLM (Phase 3) | Headless Claude Code (`claude -p`) with `--json-schema` | Chosen 2026-10-02: no API key or new dependency, and a trial on a corrupt-text Vue page matched every cell. The backend sits behind one interface, so the Anthropic Batch API stays possible (§8) |
| Models (Phase 3) | Sonnet 5.5 for 2b/2c/5; Opus 5.5 for writing parsers (dev time) | Numbers must be exact; no cheap model until it passes §9 |
| Orchestration | One CLI (`python -m pipeline.cli manifest|run|eval`) | Dozens of files doesn't justify a framework or database |

Not used, and why:
- **OCR (tesseract/ocrmypdf).** Embedded text is already exact. On image-only pages, vision handles dense grids and icon ticks better than tesseract.
- **pdfplumber, Camelot, Docling.** Add one only if poppler's word boxes can't handle a layout (e.g. filled-cell markers that need rectangles).
- **LangChain or agent frameworks.** Extraction is one structured call per page.

## 7. Repository layout

```
schemas/columns.yaml               # column dictionary (committed)
config/chains.yaml                 # chains, sources, markers, approval (committed)
config/pearlscan_columns.yaml      # ground-truth column mapping (committed)
config/ground_truth_errata.yaml    # confirmed Pearl Scan errors (committed)
golden/<pdf-stem>.csv              # hand-verified allergen rows (committed)
pipeline/
  cli.py                           # manifest | run | eval
  columns.py                       # dictionary → Pydantic row model
  ingest.py                        # pdftotext text/words, hashes, chains config
  allergens.py                     # "Contains / May contain" text → allergen cells
  validate.py, export.py           # checks, flags, per-chain CSV
  evaluate.py                      # ground truth + golden comparison
  parsers/<layout>.py              # premier_inn_breakfast, whitbread_drinks_grid, numeric_table
  extract.py                       # Phase 3: LLM routes + cache
inputs/                            # gitignored: PDFs; inputs/ground-truth/ = Pearl Scan CSVs
outputs/<id>_<Key>.csv             # gitignored
work/                              # gitignored: manifest, LLM cache
```

Git holds code, schemas, config and golden rows only. Data is gitignored, so tests that read PDFs need a local `inputs/`.

Cache key for an LLM result: `sha256(page_text_or_png) + columns.version + prompt_version + model`.

## 8. Estimated token cost and backend options

### Per full run over the current 35 PDFs

Assumptions: about 3.3 characters per token for number-heavy text, and about 2.3k tokens per page image. These are rough figures; confirm them with Phase 3.

| Path | Input tokens | Output tokens |
|---|---|---|
| 2a Parser (27 files, ~390 pp) | 0 | 0 |
| 2b LLM text (7 files, ~25 pp, ~55k chars) | ~17k content + ~50k cached prefix | ~40k |
| 2c Vision (79 pp) | ~180k images + ~15k prompts | ~90k |
| 5 Repair (assume 5% rows fail, ~40 pages) | ~130k | ~40k |
| **Total** | **~0.4M** | **~0.17M** |

A re-run with no changed inputs costs 0 tokens.

One-off setup is the largest cost: about 1–3M tokens for a coding agent to write ~10 layout parsers. It's paid once per layout, and chains tend to reuse layouts across seasons.

| Approach | Input | Output | Notes |
|---|---|---|---|
| **This design** | ~0.4M | ~0.17M | Checked numbers; unchanged files free |
| LLM on text for every page | ~1.5M | ~1M | Grids are error-prone and produce very large outputs |
| Agent reads PDFs directly | ~5–15M | ~1M | Pages cost text + image tokens; nothing cached |

### Backends

Every LLM call goes through one function, `extract(page, columns) -> rows`. Build one backend first, and add a second only if §9 shows a cheaper model is good enough.

| Backend | Cost | Use for |
|---|---|---|
| **Anthropic Batch API** (default) | List price × 0.5; cached prefix ~10% | Scheduled and recurring runs |
| **Headless Claude Code** (`claude -p`) | Pro/Max quota; per-call system-prompt overhead; 5-hour and weekly caps | Development, one-off runs, parser authoring |
| **OpenRouter** | Provider price + small fee; Claude costs ~2× the Batch API | Testing cheaper non-Claude models against §9 |

**Decision (2026-10-02): backend 1 is headless Claude Code.** A one-page trial (Vue ice cream, image via the `Read` tool, structured output via `--json-schema`) returned four rows that matched the page and Pearl Scan exactly, in 11 s, at a reported $0.10 of which about 22k tokens were Claude Code's own overhead. Each call carries that overhead, so the roadmap plan measures `--bare` and trimmed tools before any run, and tests batching pages for accuracy before using it. Models are pinned by full ID (`claude-sonnet-5-5`), never an alias.

Rules:
- **Accuracy decides**, not list price.
- **Terms.** Check Anthropic's terms before running a recurring pipeline on a subscription.
- **Data policy.** On OpenRouter, restrict providers that log or train on prompts.

## 9. Accuracy and evaluation

`python -m pipeline.cli eval` runs both checks below and exits 1 on any failure.

**Nutrition vs Pearl Scan ground truth** (`inputs/ground-truth/<Chain>/<pdf-stem>[_v0.1].csv`):
- **Which file.** The newest version (`_v0.1` beats the original; `Previous/` is ignored).
- **Matching.** Rows match on the normalised name: Pearl Scan's `item_name` vs our `Product_Name + Size`. Matching is case- and punctuation-insensitive.
- **Cells compared.** Every mapped nutrient cell, plus serving size. Numbers are compared as numbers and words case-insensitively. `menu_section` isn't compared, because sections follow our naming rules (§4).
- **Source inconsistencies are flagged, not fixed.** Pearl Scan's values match the PDF cell for cell, yet some PDFs print figures that fail the arithmetic checks (Five Guys: Lettuce is 58 kJ but 19 kcal; Relish has 0.2 saturates but 0 fat). The row is flagged and the value kept. Treat `flags` as a data-quality report on the source, not only on our extraction.

**Gate.** At least 99% of ground-truth rows matched, and 100% of matched cells agreeing, apart from `ground_truth_errata.yaml` entries.
- **Why 100%.** Values are copied, not calculated, so any difference is either our bug or a Pearl Scan error. The ground truth does contain errors: Vue `_v0.1` has kJ `82` next to 197 kcal, and Odeon had 73 typos before review. A person confirms each one against the PDF before adding it to the errata file.

**Allergens vs golden rows** (`golden/<pdf-stem>.csv`):
- Pearl Scan has no allergens, so a person checks 6–8 rows per distinct PDF against the rendered page.
- Those rows must match exactly, every allergen cell included.

**Allergen rule.** An allergen cell comes only from the source and its approved key, never from inference. Every printed marker must land in exactly one cell; a test counts them.

## 10. Rollout

1. **Phase 1 (done):** the pipeline core plus the Premier Inn breakfast and Whitbread drinks layouts: three complete chain CSVs (Beefeater, Brewers Fayre, Table Table).
2. **Phase 2: remaining text-layer layouts, in slices.** 2a (`numeric_table`, Five Guys) and 2b (Pizza Express, `pdfplumber`) are done. The rest, and Phase 3, are sequenced in [the roadmap plan](superpowers/plans/2026-10-02-complete-the-pipeline.md): foundations, the allergen-matrix parser (Cineworld, Pizza Hut), Domino's, Odeon, Coffee #1 and Starbucks.
3. **Phase 3: LLM routes.**
   - The backend, cache, token budget guard and repair loop, then vision for what text can't give (**Vue, Papa John's, Krispy Kreme**, §2), then the menu layouts (Brewhouse, Cookhouse, Top Golf).
4. **Phase 4:** a flags report in the final slice (every flagged row in one file); a review/overrides loop only if the flag volume justifies it.

## 11. Open questions

Decided 2026-10-01: add `pdfplumber` (with pdfminer.six, pypdfium2, pillow, cryptography) rather than an LLM vision pass for Pizza Express, which would cost tokens on every run for a layout a parser can handle.

To revisit later:
- Menu-wide disclaimers are config-only for now. Revisit if Menu Tracker users need them in the CSV.
- Section names in `numeric_table`: a heading is a leading ALL-CAPS run followed by nothing or a `- note`. Pearl Scan's section names for Five Guys include artifacts (`MILKSHAKES (MIX-INS) amount of`), so `menu_section` is not compared in `eval`.
- The heading-nesting heuristic in grid layouts joins consecutive headings ("SPIRITS - GIN"). A single heading after an item doesn't inherit its parent ("VODKA", not "SPIRITS - VODKA"). Revisit if users need the full hierarchy.

## 12. Decision log (2026-10-01 design review)

| # | Decision |
|---|---|
| Q1 | One CSV per chain, `outputs/<id>_<Key>.csv`, in the Costa sample's style |
| Q2 | Costa header is a starting point; a shared column dictionary is extended as needed; no unit/basis conversion |
| Q3 | Allergen values `Yes` / `May contain` / `No` (declared only) / blank; per-source marker key; unknown marker = error |
| Q4 | `region` (`UK`/`NI`/`ROI`) and `source_file` on every row; rows never merged across regions |
| Q5 | Pearl Scan reviewer comments first, then: names as printed minus layout artifacts; source typos kept |
| Q6 | Nutrient cells as printed (number, `<x`, or a dictionary word); others flagged |
| Q7 | `<nutrient>_<basis>` with dictionary bases; synonyms map to one basis; unknown basis = error |
| Q8 | `Serving_Size` + `Serving_Size_Unit` for amounts; `Size` for named sizes; descriptive portions stay in the name |
| Q9 | Chain keys from `menutracker.ipynb`, kept in `config/chains.yaml` |
| Q10 | Menu-wide disclaimers in config only, not in the CSV |
| Q11 | Ground-truth gate: ≥99% rows matched, 100% cells agree apart from confirmed errata; golden rows for allergens |
| Q12 | Phase 1 delivers complete chains: breakfast + drinks for Beefeater, Brewers Fayre, Table Table |
| Q13 | `pdfplumber` added for character-level cells (slice 2b); `numeric_table` uses it for every table PDF |

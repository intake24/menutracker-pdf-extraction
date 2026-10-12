# Start here

For new developers and for AI agents working in this repository. Read this page first; it says what the project is, how a PDF becomes a CSV, where each piece of code and configuration lives, the rules we work by, and which other document to open for which question.

## 1. What this project does

Menu Tracker collects allergen and nutrition PDFs published by UK food chains. This pipeline turns those PDFs into one CSV per chain (`outputs/<id>_<Chain>.csv`, one row per food, drink or product), replacing a paid human service called Pearl Scan. In the first round (October 2026) 17 food chains, 35 PDFs and 8,768 rows were done.

Allergen data is safety-relevant: a wrong "No" can hurt someone. That is why the pipeline copies values as printed (three flagged clean-ups, rule 1), never guesses, and stops with an error when it meets something it does not know.

## 2. Which document to read

| Question | Document | Status |
|---|---|---|
| What was done, how good is it, what are the known limits, how do I run a batch without Pearl Scan? | `end-of-round-report-2026-10.md` | Current. Read second. |
| How do I add a chain or a layout? Which parser fits which layout? | `playbook-new-batches.md` | Current |
| What does each chain's CSV contain and which decisions were taken? | `chain-mapping-reference.md` | Current |
| What went wrong in each source (PDF oddities, Pearl Scan mistakes, pipeline bugs)? | `findings-report-2026-10.md` | Current record |
| How much does a model-read round cost on the SDK? | `sdk-cost-estimate-2026-10.md` | Current (rates from 2026-10-06) |
| What was the original design and why? | `pipeline-design.md` | Historical (2026-10-01): the architecture still holds; the details of stages, backends and rollout were overtaken by the code |
| What were the implementation plans? | `superpowers/plans/` | Historical |
| Where did the last session stop? | `handoff-next-window.md` | Current |

## 3. How a PDF becomes a CSV

```
inputs/*.pdf
   |  python -m pipeline.cli manifest        pages, text, assigned parser -> work/manifest.csv
   v
config/chains.yaml                           one entry per chain; one source per PDF (or per page range)
   |  python -m pipeline.cli run             only sources with approved: true
   v
parser (pipeline/parsers/<layout>.py)        text-layer parsers read words and positions with pdfplumber;
   |                                         vision parsers send the page image to a model (pipeline/llm.py)
   v
rows (dicts)  ->  merge_by_key (optional)  ->  finalise (pipeline/export.py)
   |                                         column dictionary, arithmetic checks -> flags, duplicate check
   v
outputs/<id>_<Chain>.csv  (+ outputs/data-dictionary/_flags.csv and _verification.csv from `flags` and `report`)
   |
   v
checks: eval (Pearl Scan + golden rows), coverage, pages, reread, report, flags
   |
   v
a person sets approved: true in config/chains.yaml
```

Two kinds of reading: **text-layer parsers** (most PDFs) are deterministic and cost nothing; **vision parsers** (`vision_table`, `vision_products`, `vision_pairs`) are used only where the PDF has no usable text, and every page read is cached in `work/llm/`, so re-running costs nothing.

Pearl Scan's CSVs in `inputs/ground-truth/` are never used to produce values. Only `eval` and `report` read them, to compare. See section 2b of the end-of-round report.

## 3b. Folders and a new batch

| Folder | Holds | In git |
|---|---|---|
| `inputs/` | The PDFs ready for extraction. `inputs/ground-truth/` holds Pearl Scan CSVs, used only by `eval` to cross-check and to improve the pipeline; a batch without them still runs | no |
| `outputs/` | One CSV per chain | no |
| `outputs/data-dictionary/` | What describes the batch: `_flags.csv` and `_verification.csv` (written by `flags` and `report`), and the batch's `findings-report-<batch>.md` and `end-of-round-report-<batch>.md` (written by the agent at the end of the round) | no |
| `golden/` | Hand-checked sample rows, one file per PDF. It is the evidence behind each `approved: true` in `config/chains.yaml`, so it grows from batch to batch and stays at the root | yes |
| `work/` | Caches: model answers (`work/llm/`), rendered pages, `manifest.csv`. Keep it: it saves time and tokens | no |

To start a batch: clear `inputs/` and `outputs/`, copy the new PDFs into `inputs/`, run `manifest`, and work through the steps in section 7. Do not clear `golden/`, `work/` or `config/`. The manifest records every file name together with its hash, so a PDF with the same name as one from an earlier batch but different content shows as `changed` and the old version stays on record as `superseded` or `gone`.

The two reports of the October 2026 round stay in `docs/` as the committed record of that round. Reports for later batches go to `outputs/data-dictionary/`, which git ignores: copy them elsewhere if you want them versioned.

## 4. Code map

| Path | What it is |
|---|---|
| `pipeline/cli.py` | The commands (section 6) and the run loop: parse every source of an approved chain, merge, finalise, write the CSV |
| `pipeline/ingest.py` | PDF text and words (pdftotext, pdfplumber), loading `chains.yaml`, the manifest |
| `pipeline/columns.py`, `schemas/columns.yaml` | The column dictionary shared by every CSV: allowed columns, their order, nutrient bases, allergen columns |
| `pipeline/allergens.py` | Turns printed allergen text ("Contains: Wheat, Milk") into allergen cells; an unknown word raises |
| `pipeline/validate.py` | Arithmetic checks (kJ against kcal, saturates against fat, sugars against carbohydrate, Atwater estimate) and the duplicate check; results go to `flags`, values never change |
| `pipeline/export.py` | `finalise` (checks every row against the dictionary), `merge_by_key`, `write_csv` |
| `pipeline/evaluate.py` | Comparison with Pearl Scan (cells, rows, errata, known gaps) and with golden rows |
| `pipeline/coverage.py`, `pipeline/vision_check.py` | Checks that need no ground truth: rows against the text layer per page, and comparison of two reads of a model-read page |
| `pipeline/llm.py` | The model backend: headless Claude Code or the Anthropic SDK, one shared cache, cost cap |
| `pipeline/parsers/` | One parser per PDF layout (table below). Registered in `parsers/__init__.py` |
| `config/chains.yaml` | Every chain, source and option (section 5) |
| `config/ground_truth_errata.yaml` | Pearl Scan mistakes, each confirmed against the PDF page with the reason |
| `config/pearlscan_columns.yaml` | Which Pearl Scan column maps to which of our columns (used by `eval` only) |
| `golden/<pdf stem>.csv` | Hand-checked sample rows: allergens, diet cells, nutrition figures |
| `tests/` | The test suite (offline; the model backends are blocked by `tests/conftest.py`) |
| `inputs/`, `outputs/`, `work/`, `samples/` | Local data, never committed |

### Parsers

| Parser | Layout it reads | Used by |
|---|---|---|
| `numeric_table` | A name followed by a run of numbers, with many options for wrapped names, titles, sub-sections and odd printing | Five Guys, Pizza Express, Domino's sides, Odeon nutrition |
| `premier_inn_breakfast`, `whitbread_drinks_grid` | The Whitbread breakfast allergen list and the drinks allergen grid | Beefeater, Brewers Fayre, Table Table |
| `allergen_matrix` | Marks under rotated allergen labels, size groups, merged cells | Cineworld |
| `product_matrix` | One band per product between rules, text columns and 18 figure columns | Odeon pre-packed |
| `grouped_table` | Labels printed once beside several rows (pizza, cheese, crust, size) | Domino's pizzas |
| `portion_tables`, `mark_table` | Pizza Hut nutrition tables of several widths, and its allergen tables with circle marks | Pizza Hut |
| `product_blocks` | One block per product: name, declaration with bold allergens, nutrition column | Coffee #1 food |
| `drink_tables` | Name and allergens once beside size rows, nine figures per group, rotated titles | Coffee #1 drinks |
| `guide_rows`, `modifier_matrix` | Rows with a summary column of allergens; calories with drawn ticks | Starbucks |
| `vision_table` | A flat table read from the page image; with `text_check` for menus | Vue, Brewhouse, Cookhouse, Top Golf |
| `vision_products` | Product sheets (variant table plus allergen text) read from images | Papa John's, Domino's page 2 |
| `vision_pairs` | An allergen matrix page and a nutrition page joined row by row | Krispy Kreme |

## 5. The configuration in one page

`config/chains.yaml` is keyed by chain (`17_Brewersfayre`: Menu Tracker's id and key) and holds `chain`, optionally `merge_by_key: true`, and a list of `sources`. Each source is one PDF, or one page range of a PDF. The options every source has:

| Option | Meaning |
|---|---|
| `pdf`, `parser`, `region`, `category` | The file in `inputs/`, which parser reads it, UK, NI or ROI, and food, drinks or breakfast |
| `approved` | `true` only when a person has accepted the source. `run` skips any chain with an unapproved source |
| `markers` | What a mark means and what an unmarked allergen cell means, copied from the PDF's own key. `{'': 'No'}` only where the PDF says every allergen is listed; otherwise blank (not stated) |
| `pages` | Pages to read (numbers and `a-b` ranges) |

Parser-specific options are documented in the docstring at the top of each parser module; read that docstring before touching an option. `heading_units` (nutrient -> unit, as the column headings declare them) lets `strip_units` remove that unit from the cells. `drop_rows` (a list of exact product names) removes rows from a source after parsing: the research team does not want a row such as Cookhouse's "Swap chips & onion rings for a fresh mixed salad", a choice that saves calories rather than a food. Options that only affect `eval` and never the CSV: `pearlscan` (column overrides), `name_fixes` (names Pearl Scan reworded), `known_gaps` (how many Pearl Scan rows may stay unmatched, with the reason in a comment).

`config/pearlscan_columns.yaml` is the translation table from Pearl Scan's column names (`kj`, `satfat`, `kcal_100`) to ours. Only `eval` reads it; `run` and the parsers never do, so it has no effect on `outputs/`. A column mapped to `~` is not compared. A source's `pearlscan` option is merged over this table for that source only (for example `pearlscan: { 'slice/portion/piece': ~ }` skips a column Pearl Scan files differently). With no Pearl Scan data for a batch, this file and the `pearlscan`, `name_fixes` and `known_gaps` options are unused.

Rule of thumb: if a PDF is a new layout, add an option or a parser with a test; never special-case a product name in code.

## 6. Commands

Run them with `uv run python -m pipeline.cli <command>` (or `.venv/bin/python -m pipeline.cli <command>`). `--backend claude-code|sdk` before the command chooses the model backend.

| Command | Use |
|---|---|
| `manifest` | List every PDF with its parser, and say which PDFs are `new` or `changed` since the last manifest and which are `unassigned`; run it after new PDFs arrive and after editing `chains.yaml` |
| `scaffold --chain KEY --pdf FILE [--out FILE]` | Print a draft `chains.yaml` entry for a new or updated PDF (section 7); it edits nothing |
| `run [--chain KEY]` | Build the CSVs of approved chains. A chain that is skipped or stopped has its old CSV moved to `outputs/_stale/` |
| `eval [--lenient]` | Compare with Pearl Scan and golden rows. Fails when a source has nothing to compare against |
| `coverage` | Rows against the text layer per page; lists pages to look at |
| `pages --chain KEY` | Per page of a model-read chain: rows, errors, empty cells (no model calls) |
| `reread --chain KEY --pages N,M\|all --dpi D` | Read model-read pages again at another resolution and list differences; logged in `work/reread_log.csv` |
| `flags` | Every flagged row of every chain -> `outputs/data-dictionary/_flags.csv` |
| `report` | One line per PDF: rows, flags, golden rows, Pearl Scan, model-read and reread pages -> `outputs/data-dictionary/_verification.csv` |
| `golden --chain KEY --pdf-stem STEM --rows "Name\|Size;Name"` | Write a golden file with every value column for chosen rows; check each cell against the page by hand |

Tests: `uv run pytest` (about two minutes; they read PDFs from `inputs/`). If `pytest` is not found, use `.venv/bin/python -m pytest`.

## 7. Common tasks

**When new PDFs arrive or a chain publishes a newer issue.** Nobody and nothing edits `config/chains.yaml` automatically: a developer or agent does, and a person approves. The intake steps:

1. Put the PDFs in `inputs/` (the scraper does this).
2. Run `python -m pipeline.cli manifest`. It prints how many PDFs are `new` (not in the previous manifest), `changed` (same file name but different text or bytes, for example a replaced PDF) and `unassigned` (no source in the config), lists them, and tells you the next command. A file with a new name also shows as `new` (and, once the old file is gone, the old name is printed as `removed`).
3. For each new or changed PDF run `python -m pipeline.cli scaffold --chain KEY --pdf FILE`. The chain key is `<id>_<Name>` from Menu Tracker's `menutracker.ipynb`; for a chain that already exists use its key from `config/chains.yaml`. The command prints a draft and edits nothing (`--out FILE` also saves it).
   - **Updated issue of a known document** (the file name differs only in a date, month or version): the draft copies the matching source with the new file name and `approved: false`. The layout is probably unchanged. It also tells you which golden file belongs to the old file, to copy and re-check.
   - **A new document of a known chain, or a new chain:** the draft is a skeleton with `parser: TODO`, plus comments that list the parsers that fit the layout features (no text layer, many figure lines, printed marks) with the reason. Choose by looking at the rendered pages and the parser table in section 4; the list is a hint.
4. Paste the draft into `config/chains.yaml`, run the chain on an approved copy of the config, and follow the checks in the end-of-round report section 4. If the PDF replaced an older issue, remove the old source when the new one is approved. Copy or rename the golden file and any Pearl Scan lookups, which are named after the PDF file.
5. A person sets `approved: true`. Then `run` and `eval`.

If the layout changed, text-layer parsers usually stop with an error that says what they did not expect; that is the intended behaviour. A model-read source has fewer such guards, so run `reread --pages all` and look at the pages `coverage` lists.

**Add a chain.** Follow `playbook-new-batches.md` section 2 and the end-of-round report section 4: manifest, look at rendered pages (`pdftoppm -r 80`), choose a parser, add the source with `approved: false`, run it on an approved copy of the config (see `chains_file` in `tests/test_cli.py`), read every flag, write golden rows with `golden`, ask for a fresh review, then a person approves.

**Add a parser.** Write the test first (a synthetic page built from words and a test on the real page), put the layout description and the options in the module docstring, register it in `parsers/__init__.py`, make every unexpected situation raise a `ValueError` that says what and where, and add a row to the table above.

**Understand a flag.** `error:` flags are checks that failed (kJ against kcal, saturates above fat, a value that is not a number); `warn:` flags are softer (Atwater estimate, a name that differs a little). Most come from figures the PDF itself prints that do not add up; the value is kept as printed. Find the row in `outputs/data-dictionary/_flags.csv`, then the page in the PDF. The Atwater check, for example, estimates calories from protein, carbohydrate, fat and fibre and compares them with the printed calories; it is a calculation on the row's own figures, not data from the PDF or the model.

**Read a page the model reads.** Render it (`pdftoppm -r 150 -f N -l N -png file.pdf out`), compare with the row in the CSV, and run `reread` on the page.

**Choose the model backend.** Default `claude-code` (headless `claude -p`, plan login). `--backend sdk` or `PIPELINE_LLM_BACKEND=sdk` uses the Anthropic API (needs `ANTHROPIC_API_KEY` and `uv sync --extra sdk`). Both share one cache in `work/llm/`. Cost: `sdk-cost-estimate-2026-10.md`.

**A run stopped.** Rate limit, cost cap or a failed check stops the chain and prints why; every finished page is cached, so run the same command again to continue.

## 8. Rules we work by

For people and agents alike:

1. **Values as printed.** No unit conversion, no rounding, no fixing typos. A problem goes into `flags`; the value stays. The only exceptions are the clean-ups in `pipeline/export.py` (`normalise`), set by the research team: a unit that the PDF's column heading declares is removed from the cell ("Sodium (mg)": `108mg` becomes `108`; the headings are listed per source in the `heading_units` option), while any other unit and markers such as `*` or `#N/A` stay as printed and are flagged; a decimal comma becomes a point (`1,75` becomes `1.75`), and in kJ and kcal a comma before exactly three digits is a thousands comma and is removed (`1,702` becomes `1702`); and `1/2` in `Recommended_Portions` becomes `0.5`. Each one is flagged.
2. **Unknown means stop.** An unknown allergen word, label, marker, column or diet word raises. Never map an unknown thing to a guess.
3. **A blank allergen cell means "not stated".** `No` only where the PDF declares the allergen absent (`markers`).
4. **Similar products stay separate rows.** Merge only when very likely the same product, and say so in `notes`.
5. **Pearl Scan is a cross-check, not the authority.** The PDF page decides; record any Pearl Scan mistake in `ground_truth_errata.yaml` with the reason.
6. **People hold the gates.** Setting `approved: true` and checking golden rows against pages are decisions for the user, not for the agent that wrote the code.
7. **Never delete or overwrite local data** (`inputs/`, `outputs/`, `work/`, `golden/`, `samples/`). Move or copy instead. An earlier session deleted sample files by mistake.
8. **Test first** for every parser or rule: watch the test fail, then make it pass; run the whole suite before committing, and run it on its own (do not chain it with `&&` before a commit).
9. **One branch per slice of work**, merged fast-forward into `main` when the tests pass. Commit messages carry no `Co-Authored-By` trailer and no "generated with" line.
10. **A fresh reviewer** (a different agent, the strongest available model) reviews every new parser and anything that touches allergens or the model route; fix Critical and Important findings with tests that fail first.
11. **Model calls cost money or quota.** Tests never call a real model (`tests/conftest.py` blocks both backends); use the cache, and read pages from the cache with `pages` before asking again.
12. **Document as you go.** After a new chain add a row to `chain-mapping-reference.md`, an entry to `findings-report-2026-10.md` and update the totals and the handoff. In Markdown files write one line per paragraph (no hard wrapping at a column count).

## 9. Glossary

| Term | Meaning |
|---|---|
| Golden rows | A hand-checked sample of rows in `golden/`, with allergens, diet cells and figures. `eval` requires an exact match |
| Errata | Pearl Scan mistakes confirmed against the PDF, in `config/ground_truth_errata.yaml` |
| `known_gaps` | The number of Pearl Scan rows that may stay unmatched in `eval` because their names differ (each with a stated reason) |
| `text_check` | For model-read menus: every figure printed in the text layer must be a row the model returned, and the other way round |
| Mark accounting | Counting the marks printed on a page against the marks the parser used |
| `reread` | A second model read of a page at a higher resolution, compared cell by cell with the first |
| Stale CSV | An old output of a chain that was skipped or stopped; moved to `outputs/_stale/` |
| Merged product | A row built from two sources (allergen table and nutrition table) that are very likely the same product; `notes` says so |
| Text layer | The text stored in the PDF; where it is missing or corrupt, the page image is read by a model |

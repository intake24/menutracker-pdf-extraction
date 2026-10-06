# End-of-round report: October 2026 (17 food chains)

Written 2026-10-06. Related documents: `findings-report-2026-10.md` (what we found in each source), `chain-mapping-reference.md` (how each chain's PDFs map to the CSV), `playbook-new-batches.md` (how to add a chain), `sdk-cost-estimate-2026-10.md` (cost of a round on the Anthropic SDK) and `handoff-next-window.md`.

## 1. Result

All 17 food chains are extracted, approved and saved in `outputs/`: 17 CSV files, 8,768 rows, from 35 PDFs. The 304 tests pass, and `eval` passes with every source checked.

Where Pearl Scan also has a nutrition figure, ours matches it, apart from 75 Pearl Scan mistakes (listed in `config/ground_truth_errata.yaml`) and a few name differences we accepted (40 on the Cookhouse main menu, 12 on Top Golf). Every Pearl Scan figure on those two menus is still among our rows.

Pearl Scan has no allergen data for most chains, so allergens are checked in four other ways:

- **Golden rows:** sample rows read by hand from the page images.
- **Mark accounting:** every mark printed on a page must be used by a row.
- **Two readings of one statement:** Starbucks prints allergens twice, in a summary column and in bold capitals, and the two must agree.
- **Second reads:** pages read by the model are read again at a higher resolution, and any difference is looked at.

## 2. What the round found

**Pearl Scan is a cross-check, not the authority.** It dropped or reworded names, invented serving sizes, changed printed values (`<0,005` became `<0.005`, `1,702` became `1702`, `1/2` became a date), swapped counts, renamed add-ons, and left out figures printed inside descriptions.

**The pipeline made mistakes too.** Comparison with Pearl Scan and fresh Opus reviews found, among others:

- the last row of a page silently lost (three times, on three layouts);
- a one-word heading mistaken for a column header;
- allergens attached to the wrong product when a rule line was missing;
- "gluten free oats" marked as containing gluten;
- "May containMILK", printed without a space, read as "No" for milk;
- categories carried onto the wrong page.

Each one was fixed with a test that failed first.

**Model reads of small print are unreliable.** 23% of the figures on Domino's page 2 were wrong, so figures now come from the text layer wherever there is one, and the model only reads labels. For menus, every figure printed in the text layer must appear in a row the model returned (`text_check`). An answer that fails the check is not saved.

## 2b. Independence from Pearl Scan

**The values in `outputs/` come from the pipeline alone.** Only `eval` and `report` read `inputs/ground-truth/`, to compare and to describe. `run`, the parsers and the model calls never read it, so deleting that folder would give identical CSVs (checked in the code, and `eval` was run against an empty folder).

**Pearl Scan did shape how the pipeline was built.** While building each parser we compared its output with Pearl Scan and fixed what differed. Pearl Scan's row counts caught three silent losses of a page's last row (Coffee #1, Starbucks, Domino's). The menu naming rules (add-ons keep their own name, options are "<dish> - <option>") were written partly to match its conventions. Sixteen settings in `config/chains.yaml` (`name_fixes`, `known_gaps`, `pearlscan`) exist only to line names and columns up for `eval` and do not change the CSVs. The 75 recorded Pearl Scan mistakes decided which differences we treated as Pearl Scan's fault.

**What to expect from the next batch.** This round's accuracy (every shared figure agreeing, apart from 75 Pearl Scan mistakes) is an upper bound, not a promise.

| Expect to hold | Expect to be weaker |
|---|---|
| Same chains and layouts: the same rules and parsers, so quality close to this round | A new layout: no parser yet, and a silently lost row is no longer caught by Pearl Scan's row counts |
| Text-layer sources: deterministic, the same result on every run | Model-read pages: only the arithmetic flags and the second read back up the figures |
| Menus: the text-layer figure count (`text_check`) | Names and the naming of add-ons and options: nothing to compare them with |

The checks in section 4 replace Pearl Scan, and each is weaker than a full comparison, so plan on more review for any new layout.

## 3. How the data is mapped

The full detail is in `chain-mapping-reference.md`. The main rules are:

- One row per product, or per size or variant where the PDF prints one.
- Values are kept exactly as printed.
- An allergen cell is Yes, May contain, No (only where the PDF says every allergen is listed) or blank.
- Diet cells are kept as printed.
- `Category` is the heading path as printed.
- `notes` holds printed notes and remarks such as "Add-on to ..." or "Merged product: ...".
- Every row records its source file, page, method and any flags.

Similar products stay separate. Two rows are merged only when they are very likely the same product: same name, size, region and heading, no cell filled in both, and exactly one partner each way. A merged row says so in `notes`.

## 4. Running a new batch without Pearl Scan

1. Put the PDFs in `inputs/` and run `python -m pipeline.cli manifest`. Look at two or three rendered pages of each PDF, choose a parser from the table in the mapping reference, and add the source to `config/chains.yaml` with `approved: false`.
2. Run the chain on a temporary approved copy of the config (see `chains_file` in `tests/test_cli.py`). Read every flag, then run `coverage` for text-layer PDFs, or `pages` and `reread` for model-read PDFs.
3. Read the PDF's introduction and key pages to learn what a blank allergen cell means, and set `markers` to match.
4. Write golden rows from the rendered page: allergens, diet cells and a few nutrition figures. Check the figures against `pdftotext` or the page image, not against the parser. Include a "may contain" row, an empty row and an unusual row.
5. Have a fresh Opus reviewer review any new parser and anything that touches allergens or the model. Fix Critical and Important findings with tests that fail first.
6. Run `report` (one line per PDF) and `flags` (every flagged row). A person approves the source in `config/chains.yaml`. Then run `run` and `eval`.

## 5. Commands

| Command | What it does |
|---|---|
| `manifest` | Lists every PDF with its pages, text and assigned parser |
| `run [--chain KEY]` | Extracts every approved chain into `outputs/` |
| `eval [--lenient]` | Compares outputs with Pearl Scan and golden rows. Strict by default: a source with nothing to compare against fails |
| `coverage` | Finds text-layer pages with more data lines than rows, and lists pages (any layout) with fewer rows than the text layer suggests, as a list to look at |
| `pages --chain KEY` | Per page of a model-read chain: rows, errors, empty cells |
| `reread --chain KEY --pages N,M\|all --dpi D` | Reads pages again at another resolution and lists differences; every page read is logged in `work/reread_log.csv` |
| `flags` | Writes every flagged row to `outputs/_flags.csv` |
| `report` | Writes one line per PDF to `outputs/_verification.csv` (rows, flags, exact duplicates, golden rows, Pearl Scan present, model-read pages, pages reread and differences found) |
| `golden --chain KEY --pdf-stem STEM --rows "Name\|Size;Name"` | Writes a golden file with every value column (allergens, diet, nutrients, notes) for the chosen rows, to be checked against the page by hand |
| `--backend claude-code\|sdk` (before any command) | Chooses how the model reads pages: headless Claude Code (default) or the Anthropic SDK; or set `PIPELINE_LLM_BACKEND` |

If a chain is skipped (not approved) or stopped (rate limit, cost cap or a failed check), its old CSV is moved to `outputs/_stale/`, so no report or evaluation mistakes it for current output.

## 6. Final review (fresh Opus, 2026-10-06)

### Fixed, with tests

- Two image-only PDFs could share one parse result. The cache key now includes the file's contents.
- A skipped or stopped chain left its old CSV looking current. It is now moved aside.
- `vision_pairs` failed on a PDF name containing a dot.
- `eval` could pass with nothing checked. It is now strict by default.

### Known limits (not changed)

| Limit | Risk if it goes wrong | What to do |
|---|---|---|
| The V/VE tag check on menus runs only where the text layer prints a tag next to every use of a figure (57 of 126 Brewhouse rows) | A tag the model invented on an untagged dish passes | Check by eye the three rows the text layer does not confirm: Korean Hot and two poached egg add-ons |
| Krispy Kreme, Papa John's and Vue figures have no second check without Pearl Scan beyond the arithmetic flags and the higher-resolution reread; their golden files hold allergens only (Vue has none) | A consistent misread that still adds up would pass | Reread every page of such a source and add figure rows to its golden file |
| `eval` compares from the reference side only | An extra or invented row in our output does not fail | Use `coverage`, row counts from `report`, and `text_check` on menus |
| Recall of 99% passes even when up to 1% of Pearl Scan rows are unmatched and `known_gaps` is 0 | A few rows missing on a large file | Each source was inspected when approved |
| The model call loads the user's Claude settings (`--setting-sources user`) | Answers could depend on installed plugins, and the cache key does not include them. Risk is low; `notes` text is the most exposed | Move to the SDK, which has no such settings |
| The cache key includes the image path and the rendered image bytes | Moving the repository or upgrading poppler repeats every model call (a cost, not a correctness problem) | None needed |
| Exact duplicate rows are counted in `report`, not flagged | Most are real repeats, such as adult and kids Fries; a rise in a model-read source suggests a double read | Watch the count |
| `text_check` ignores figures such as 2000 kcal on both sides (Brewhouse 2000; Cookhouse 1800 and 2000) | A real dish at that figure could be dropped unnoticed | Check those figures by eye |
| When one PDF feeds several sources, only the first source's `name_fixes` and `pearlscan` options apply | None today | Keep in mind when adding sources |
| The cost cap can be overshot by the parallel calls in flight | At most about $1.50 | None needed |
| `eval` treats `0.10` and `0.1` as equal | Formatting changes would pass `eval` | The parsers and their tests protect the "as printed" rule |

## 6b. Improvements made before the next batch

- **Per-page row check for every layout:** `coverage` now compares each page's rows with the data-looking lines of the text layer for any layout (it scales to layouts with several lines per row). On this round's outputs it lists 14 pages, all checked and none a loss (intro pages, a wrapped line, shared-row tables).
- **Golden files with figures:** all golden files now carry nutrient columns, and `golden` writes new ones with every value column. The figures in the existing files come from the pipeline output, which agreed with Pearl Scan this round; for a new batch each figure must be checked against the page or `pdftotext`.
- **Reread as a standard step:** `reread --pages all` covers every model-read page and logs it; `report` shows how many pages were reread and how many differences. Before approving a model-read source the "reread" column should equal the "model pages" column. This round's rereads were run by hand and are not in the log, so the column shows 0.
- **Choice of model backend:** headless Claude Code or the Anthropic SDK, `--backend` or `PIPELINE_LLM_BACKEND`, one shared cache. The SDK path is tested with a fake client and has not yet made a real call (no API key was available here): run one page with `--backend sdk` and compare it with the cached headless answer before relying on it.

## 7. What remains

Nothing is blocked. For the next batch, expect no Pearl Scan data and spend the effort on three things:

- golden rows that include nutrition figures;
- a reread of every model-read page;
- a second person spot-checking the golden rows. They are generated from pipeline output and then checked against page images by one reader.

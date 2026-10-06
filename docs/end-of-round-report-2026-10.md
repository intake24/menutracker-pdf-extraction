# End-of-round report: October 2026 round (17 food chains)

Written 2026-10-06. Companion documents: `docs/findings-report-2026-10.md` (per source: what was odd, what Pearl Scan got wrong, what the pipeline got wrong), `docs/chain-mapping-reference.md` (what each chain's PDFs map to in the CSV and the decisions behind it), `docs/playbook-new-batches.md` (how to onboard a chain), `docs/handoff-next-window.md`.

## 1. Result

All 17 food chains are extracted, approved by the user and in `outputs/`: 17 CSVs, 8,768 rows, from 35 PDFs. 304 tests pass and `python -m pipeline.cli eval` passes with every source evaluated (strict is now the default).

Every nutrition figure that Pearl Scan also holds agrees with it except 75 recorded Pearl Scan mistakes (`config/ground_truth_errata.yaml`) and a few allowed name differences (`known_gaps`: Cookhouse main menu 40 names, Top Golf 12 names; every Pearl Scan figure is among our rows).

Allergen data has no Pearl Scan equivalent for most chains; it is checked by golden rows (hand-read from page images), by mark accounting (every printed mark is used by a row), by a second independent reading where the PDF prints allergens twice (Starbucks summary column against bold capitals), and by second reads of model-read pages at a higher resolution.

## 2. What the round found (summary; details in the findings report)

Pearl Scan made recurring mistakes: dropped or reworded names, invented serving sizes, changed printed values (`<0,005` to `<0.005`, `1,702` to `1702`, `1/2` to a date), swapped counts, curated names for options and add-ons, and left out figures printed inside descriptions. It is a useful cross-check for nutrition, not the authority.

The pipeline made its own mistakes, found by comparison and by fresh Opus reviews of every slice that touched allergens or the model route: silent loss of the last row of a page (three times, on three layouts), a one-word heading swallowed as a header, allergens landing on the wrong product when a rule is missing, "gluten free oats" setting gluten, a "May containMILK" printed without a space read as No, wrong categories carried across pages, duplicate checks that hid or invented conflicts, and a golden comparison that skipped sibling rows. Each was fixed with a test that failed first.

A model read of tiny print is unreliable (23% of Domino's page 2 figures were wrong), so figures come from the text layer wherever one exists and the model reads only labels. Where a text layer prints figures (menus), every printed figure must be a row the model returned (`text_check`), and an answer that fails is never cached.

## 3. How the data is mapped

See `docs/chain-mapping-reference.md`. In short: one row per product (per size or variant where the PDF prints one), values as printed, allergen cells Yes, May contain, No (only where the PDF declares every allergen is listed) or blank, diet cells as printed (`Suitable_for_*`, `Diet`), `Category` is the heading path as printed, `notes` holds printed notes and remarks (for example "Merged product: ..." or "Add-on to ..."), and every row names its `source_file`, `source_page`, `method` and `flags`.

Similar products stay separate rows. Two rows are merged only when very likely the same product (same name, size, region, heading up to punctuation or depth, no cell in both, one partner each way), and the merged row says so in `notes`.

## 4. How to run a new batch without Pearl Scan

1. Put the PDFs in `inputs/`, run `python -m pipeline.cli manifest`, look at two or three rendered pages per PDF and choose the parser from the table in the mapping reference; add a source to `config/chains.yaml` with `approved: false`.
2. Run the chain through a temporary approved copy of the config (see `tests/test_cli.py: chains_file`) and read every flag, then `coverage` (text layers) or `pages` and `reread` (model reads).
3. Read the introduction and key pages of the PDF for what a blank cell means and set `markers` accordingly.
4. Write golden rows from the rendered page: allergens and diet cells AND a few nutrition rows (compare figures with `pdftotext` or the page image, not with the parser). Cover a may-contain row, an empty row, a merged or unusual row.
5. Ask a fresh Opus reviewer to review any new parser and anything that touches allergens or the model route; fix Critical and Important findings with tests that fail first.
6. `python -m pipeline.cli report` shows one line per PDF (rows, errors, warnings, exact duplicates, golden rows, Pearl Scan present, model-read pages) and `python -m pipeline.cli flags` lists every flagged row in `outputs/_flags.csv`; a person approves in `config/chains.yaml`; `run`, then `eval` (strict by default: a source with nothing to compare against fails).

## 5. Commands

`manifest`, `run [--chain KEY]`, `eval [--lenient]`, `coverage`, `pages --chain KEY`, `reread --chain KEY --pages N,M --dpi D`, `flags`, `report`. A chain that is skipped (unapproved) or stopped (rate limit, cap, a failed check) has its old CSV moved to `outputs/_stale/` so that no report or evaluation reads it as current.

## 6. Final whole-pipeline review (fresh Opus, 2026-10-06): findings and rulings

Fixed with tests: the shared parse cache could give two image-only PDFs one result (the key now includes the file's bytes); a skipped or stopped chain left its old CSV as current (moved to `_stale`); `vision_pairs` broke on a PDF name with a dot; `eval` could pass with nothing checked (strict is the default, `--lenient` opts out).

Rulings (not changed, with the cost if wrong):

- **Dietary tag check (V/VE) on menus is partial.** It only runs where the text layer prints a tag for every use of a figure (57 of 126 Brewhouse rows); the text layer sometimes prints a tag on another line, so a stricter rule would reject correct rows. Cost if wrong: a model-invented V on an untagged dish passes (3 rows are not confirmed by the text layer: Korean Hot and two poached egg add-ons); check them by eye when approving.
- **Model-read figures of Krispy Kreme, Papa John's and Vue have no second check without Pearl Scan** beyond the arithmetic flags and the second read at a higher resolution; their golden files hold allergens only (Vue has none). Cost if wrong: a consistent misread that adds up passes. Mitigation for the next batch: run `reread` on every page of such a source and add figure rows to its golden file.
- **Evaluation compares from the reference side only** (Pearl Scan or golden rows): an extra or invented row in our output does not fail. Mitigations: `coverage`, `report` row counts per page, `text_check` on menus.
- **`recall >= 0.99` passes with up to 1% of Pearl Scan rows unmatched** when `known_gaps` is 0; every configured source was inspected when approved.
- **The model call loads the user-level Claude settings** (`--setting-sources user`), so answers can in principle depend on installed plugins; the cache key does not include that. Risk is low (a Read-only tool, structured output) but `notes` text is the most exposed field.
- **The cache key contains the absolute page-image path and the rendered image bytes**: moving the repository or upgrading poppler makes every model call run again (cost, not correctness).
- **Exact duplicate rows are counted in `report` (`exact_duplicates`), not flagged**: most are legitimate repeats (adult and kids Fries); a rise in a model-read source is a sign of a double read.
- **`ignore` in `text_check` removes a figure from both sides** (2000 kcal on Brewhouse, 1800 and 2000 on Cookhouse): a real dish at that figure could be dropped unnoticed.
- **Only the first source's `name_fixes` and `pearlscan` options apply when one PDF feeds several sources** (latent; no current source is affected).
- **The dollar cap can be overshot by up to the number of parallel calls** (at most about $1.50).
- **`same()` in evaluation ignores formatting** (`0.10` against `0.1`); the formatting rule is protected by the parsers and their tests, not by `eval`.

## 7. What remains

Nothing is blocked. For the next batch: expect no Pearl Scan, so spend the saved effort on step 4 of section 4 (golden rows with figures), `reread` of every model-read page, and a second person's spot check of the golden rows (the golden files are generated from pipeline output and then checked against page images by one reader).

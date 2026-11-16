# End-of-round report: September 2026 batch

Written 2026-11-06. Goal: `docs/goal-batch-2026-09.md`. Nutrition only, no Pearl Scan data. Details per source: `findings-report-2026-09.md`; checks per PDF: `_verification.csv`; every flagged row: `_flags.csv`.

## Result

- 19 chains produced a CSV in `outputs/`, 7,994 rows, from 35 PDFs plus 5 derived PDFs (Chicken Cottage, see the findings report). Two chains are new: Zizzi (`24_Zizzi`) and Chicken Cottage (`88_ChickenCottage`).
- Rows: Starbucks 1,686; Pizza Express 925; Zizzi 843; Odeon 808; Tesco 682; Papa John's 490; Vue 441; Cineworld 344; Tortilla 299; Pizza Hut 250; Wasabi 207; Subway 185; Cookhouse 179; Krispy Kreme 178; Top Golf 127; Brewhouse 125; Coffee #1 89; Soho 70; Chicken Cottage 66.
- Not produced: Five Guys (the PDF has no nutrition), Domino's, Real Greek, Ask Italian, Chef & Brewer, Pho, Flaming Grill, Beefeater, Brewers Fayre, Table Table (no September PDF).
- Checks: `eval` passes (golden rows of every source, 0 failures); `coverage` reports every data-looking line has a row; the full suite passes (333 tests, 75 skipped because they read PDFs of earlier batches); every model-read source has a second read (Vue, Papa John's, Krispy Kreme, Soho, Pizza Hut, Chicken Cottage and the Tortilla hot drinks page), or a `text_check` (Tesco, Cookhouse, Top Golf), and a free check that every returned figure is on the page text where the PDF has a text layer (Krispy Kreme 3,145 figures, Papa John's 7,185, Pizza Hut 1,888, Soho 629: all found after the fixes).
- Fresh reviewer: one subagent reviewed the parser changes (`numeric_table`, `product_blocks`, `guide_rows`). No Critical findings. Two Important findings and two Minor ones were fixed with tests that fail first: `blank_cells` now only applies to a label alone on its line (`Fibre -` still stops the run); the nameless-row note merge needs a bracketed note within 2.5 line heights; a registered mark joins a name only when it is in the regular font, on a bold name's line and right of it. The four affected chains were re-run and their CSVs are byte-identical.

## Code changes (all with tests)

- `numeric_table`: `wrap_below` takes a bracketed note under a row whose name is on the line above; new `wrap_below_lines`.
- `product_blocks`: `blank_cells`.
- `guide_rows`: figure cells grouped on their own; `®`/`™` handling; the "sizes for figure lines" error lists the figure lines.
- `tests/fixtures/coffee1_drink_tables_source.yaml` keeps the Coffee #1 beverage source options for `test_drink_tables.py` (the source left the config because there is no September beverage PDF).
- `tests/test_ingest.py`: expects 29 chains, and allows a PDF listed by an unapproved source.

## Model calls (approximate, from the run logs)

Papa John's 63 pages read at 150 dpi, then 63 at 200 dpi (the 200 dpi pages are now the main read); Vue 15 pages, 10 drinks pages again after the instruction change, and second reads of 15 + 10; Krispy Kreme 20 + 20; Soho 20 + 20; Pizza Hut 4 + 4; Tesco 35; Cookhouse 8; Top Golf 10; Tortilla 1 + 1; Chicken Cottage 5 + 5 + 5 + 5 (an instruction change and its second reads). No chain went beyond a rerun of all its pages twice except Papa John's (three reads of the affected pages, all in the cache) and Vue's drinks (instruction change). The 5-hour quota ran out once; runs resumed from the cache.

## Known limits

- Zizzi has no `menu_section` (titles are printed over a watermark word).
- The PDFs' own inconsistencies are flagged, not fixed: Brewhouse kJ against kcal (84 rows), Vue F'Real kJ and kcal swapped, Tortilla 36 kJ/kcal mismatches, Odeon 143 kJ/kcal mismatches, Soho `57.-` and shifted columns.
- Vue's text layer is corrupt, so its figures rest on two model reads and the golden rows checked against the page images.
- The Papa John's, Krispy Kreme, Soho and Pizza Hut second reads show only label differences or the filing of the portion weight.

## Remarks for the owner

1. **Approvals given by the agent**: every source of the 19 chains above. Sources with no September PDF (nine chains) were set to `approved: false # no September 2026 PDF`; the Five Guys source points at the new allergen-only PDF and is unapproved.
2. **Derived PDFs in `inputs/`** (your request): `ChickenCottage_BOXES.pdf`, `_BURGERS`, `_FRIED`, `_GRILLED`, `_SIDES`, made from the five JPGs (originals kept). If you would rather have `manifest` read images directly, that is a code change; say so.
3. **Doubtful calls**: (a) Brewhouse kJ and kcal disagree in most rows in the PDF; values are as printed, so a data user should not trust the kcal column without asking Brewhouse. (b) Chicken Cottage FRIES `297 kcal / 414 kcal`: the board does not say which size is which, so the rows are `1st figure` and `2nd figure`. (c) Krispy Kreme portion weights are filed as serving size and unit (the first read), as on the other pages. (d) Papa John's is read at 200 dpi because the 150 dpi read misread cells; all other pages agree between the two reads. (e) Zizzi `region: ROI` covers the guide titled "ROI.BEL" (Republic of Ireland and Belfast).
4. **Standing items for the research team**: sodium and caffeine units differ between sources (see the June notes); the `2 kcal`-style cells and the `n/a` markers are kept as printed and flagged.
5. **For the next batch (December 2026)**: print the first lines of every page before setting `pages`; use the free figure-in-page-text check for every model-read PDF with a text layer; expect page groups to shift when a section grows; check golden rows against the right source when two sources share product names. Lessons are in `docs/playbook-new-batches.md` section 5e.

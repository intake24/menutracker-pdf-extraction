# Runbook: a monthly batch (written 2026-11-16 for the November 2026 collection)

For an agent starting a new batch cold. It condenses what the March, June and September 2026 batches taught. Read `start-here.md` (rules, section 8) first, then this page, then `goal-batch-2026-11.md`. The detail behind each point is in `playbook-new-batches.md` (sections 5c to 5e) and in the September reports (`end-of-round-report-2026-09.md`, `findings-report-2026-09.md`).

## 0. State at the start (2026-11-16)

- `main` is clean and holds the September work. `inputs/` and `outputs/` still hold the September files (30 PDFs, 5 JPGs, `List_of_PDFs_Sept26.xlsx`, 5 derived `ChickenCottage_*.pdf`, 19 CSVs). Do not delete anything: archive first (step 1).
- 19 chains have an approved CSV from September (7,994 rows). Ten chains have no September PDF and are `approved: false`: Beefeater, Brewers Fayre, Table Table, Domino's, Real Greek, Flaming Grill, Ask Italian, Chef & Brewer, Pho (no PDF), Five Guys (the September PDF is an allergen-only chart with no nutrition). When a new PDF of one of them arrives, rename its source in `config/chains.yaml`, set `approved: true` only after the done criteria (step 5), and expect to fix the pages and options (the old issues are in git history; see "Recovering removed sources" below).
- The research team lists the month's PDFs in `inputs/List_of_PDFs_<Mon><YY>.xlsx` (columns: restaurant name, PDF name). Read it with `uv run --with openpyxl python`. A PDF named in the list that is not in `inputs/`, or the other way round, is a question for the owner.
- The model quota (headless `claude -p`, plan login) is a 5-hour window. A batch used most of one window in September. Finished pages are cached in `work/llm/`, so a stopped run resumes from the cache.

## 1. Intake

1. Archive the old batch outside the repo (for example `~/dev/menutracker-archive/2026-09/` with `inputs/`, `outputs/`); never delete `work/`, `golden/`, `config/`. Then copy the new PDFs flat into `inputs/` (`manifest` reads `inputs/*.pdf` only). Images (JPG) are not read: convert each to a one-page PDF named `<Chain>_<NAME>.pdf` with Pillow (`Image.save(path, "PDF", resolution=144.0)`), keep the JPG, and say so in the findings report (done for Chicken Cottage in September; the owner agreed).
2. `uv run python -m pipeline.cli manifest` lists `new`, `changed`, `unassigned`. Then, for each file, `scaffold --chain KEY --pdf FILE`. Chain keys are `<id>_<Name>` from `~/dev/menutracker/menutracker.ipynb` (Zizzi is `24_Zizzi`, Chicken Cottage `88_ChickenCottage`).
3. Write `docs/goal-batch-<yyyy>-<mm>.md` from the last goal file (intake table: chain, file, compared with last month).
4. Before any model call, print the first two lines of every page of every new PDF (`pdftotext -layout -f N -l N`) and rebuild `pages`. Page groups shift when a section grows (Wasabi, Tortilla, Papa John's, Starbucks all shifted by one in September).

## 2. Per chain: what usually changes and how to handle it

| Chain key | Parser(s) | What changed between issues so far |
|---|---|---|
| `11_PizzaExpress` | numeric_table (4 PDFs: England/Wales/Scotland, Northern Ireland, Mac & Wings, QSR Brixton) | Only file names (hashes). Row count equals text lines. |
| `46_Cineworld` | allergen_matrix | Only the file name. |
| `58_Vue` | vision_table (drinks, sweets; food and ice cream returned in earlier months) | Text layer corrupt: model reads. Packaged drinks print two figure lines per item (per 100 ml, per serving with the volume in the portion cell): the drinks instruction says so; do not edit the instruction text without meaning to re-read every page (cache key). |
| `59_Odeon` | numeric_table + product_matrix (UK; Belfast and ROI were removed in September) | The pre-packed matrix moves its columns each issue: remeasure `text_columns` and `numeric_columns` from the header words (Odeon sources in `config/chains.yaml`). |
| `26_PapaJohns` | vision_products | Pages shift; read at 200 dpi (the 150 dpi read misread cells). Keep the golden name `nutritional-information__<yyyy>-<mm>` (same file name every month). 63 pages. |
| `35_KrispyKreme` | vision_pairs | The PDF changes kind (core book, drinks book): list the pages that print "Nutrition Per 100" as `joins` with `matrix: []`. |
| `8_Pizzahut` | vision_table | Nutrition pages move (12-15, then 10-13). |
| `47_Coffee1` | product_blocks (food; beverage and birthday returned in earlier months) | Option `blank_cells` for a label with empty cells. |
| `7_Starbucks` | guide_rows (food, beverage, and a Castillo bakery book) | Seasonal books change name and version each issue; set `pages` from the survey; pages with no running head need `menus`. |
| `45_Brewhouse` | numeric_table on the text layer (September 2026) | Was a three-page model-read matrix before; if it changes shape again re-measure `section_x` and the nine columns. |
| `49_CookhousePub` | vision_table with `text_check` (main, kids, breakfast) | Same file names every month: golden names carry `__<yyyy>-<mm>`. |
| `73_TopGolf` | vision_table with `text_check` | Hidden text on one page (page_ignore). |
| `9_Subway` | numeric_table | Only the file name. |
| `79_Tortilla` | numeric_table (x2) + vision_table (hot drinks) | Titles in odd case, breakfast and drinks pages with names above the figures. |
| `69_TescoCafe` | vision_table with `text_check` | Page counts; the kcal pairs `275/355` are printed and flagged. |
| `66_SohoCoffee` | vision_table (food; drinks returned in earlier months) | 28 pages, dividers are skipped. |
| `76_Wasabi` | numeric_table x8 | Per-page `max_x` between the last figure and the first Y/N cell; page groups shift. |
| `24_Zizzi` | numeric_table x2 (UK, ROI/Belfast) | Group titles are not readable, `menu_section` blank. |
| `88_ChickenCottage` | vision_table x5 (derived PDFs from JPGs) | New boards each month; check every board image by eye (about 66 rows). |

### Recovering removed sources

Sources removed in September because their PDF was missing (Vue food and ice cream, Odeon Belfast and ROI, Coffee #1 beverage and birthday, Soho drinks, Krispy Kreme core book, Starbucks Spring books, Real Greek, Ask Italian, Chef & Brewer, Pho and others) are in git: `git show 7bf31f1:config/chains.yaml` is the June config. Copy the source block, rename the PDF, re-measure pages and columns. The Coffee #1 beverage source options are also in `tests/fixtures/coffee1_drink_tables_source.yaml`.

## 3. Procedure per chain

1. Rename the sources (`tools/cfgedit.py`, or edit the YAML), delete sources whose PDF is missing (an unapproved source stops its whole chain). Check `git diff config/chains.yaml`.
2. `run --chain KEY`. A text-layer parser stops with an error that says what it did not expect: add the option, with a test first for any code change (`playbook-new-batches.md` section 4 and the parser docstrings).
3. Check the row count against the text layer per page (lines with the expected number of figures), read the flag summary (`flags`), and look at the first flagged rows against the page: most flags are the PDF's own inconsistencies (kJ against kcal, Atwater).
4. Model-read sources: `pages --chain KEY` (free), then `reread --chain KEY --pages all --dpi 200`. Where the PDF has an intact text layer, also run `python tools/figcheck.py outputs/<chain csv> inputs/<pdf>`: every figure of every row must be on its page. In September this found a misread the reread had also shown and proved the other 20,000 figures. For a misread cell change the source `dpi` (cache key), do not edit values.
5. Golden rows: `golden --chain KEY --pdf-stem STEM --rows "Name|Size;Name"` with 3 to 9 rows including the first, the last and an odd row; check each cell against the page (`python tools/gcheck.py`, then by eye on the rendered page for model-read PDFs). **The command picks rows by name over the whole chain**, so a name shared by two sources (Pizza Express NI/England, Starbucks food/Castillo, Tesco GB/NI, Cookhouse main/kids, Vue) gives the other source's row: check the file's rows against the right PDF, and if wrong edit the file by hand (the file is new in this batch; golden files of earlier PDFs are never overwritten).
6. `eval` must pass for every source.
7. Commit after each chain (no `Co-Authored-By` trailer, per AGENTS.md).

## 4. End of the batch

`run`, `eval`, `coverage`, `flags`, `report`, the full test suite on its own (`uv run pytest -q`, about a minute: `tests/test_ingest.py` expects every PDF of `inputs/` to belong to a source and counts the chains; update the chain list in `test_one_pdf_per_source_and_twenty_nine_chains_configured` when a chain is added), a fresh reviewer for new or changed parsers (a read-only agent over `git diff <last commit of the previous batch> -- pipeline tests`; fix Critical and Important findings with tests that fail first), then the two reports in `outputs/data-dictionary/` and a copy in `docs/` (the outputs folder is not in git), the goal file status, this runbook's state section and `handoff-next-window.md`.

## 5. Practical pitfalls

- macOS `sed -i` needs a backup-suffix argument and `zsh` rejects shell functions named like aliases (`g`, `gg`): edit YAML with the Edit tool or a short Python script, and put repeated commands in a script file.
- The session scratchpad (`/private/tmp/...`) is wiped between sessions: keep helper scripts in `tools/`.
- A model run can stop at the 5-hour limit; it prints `stopped: ... resets <time>`; wait and run the same command again.
- `text_check` stops with "the text layer prints [...] that the model did not read": a figure printed without its unit (`(1498 / 2699 kcal.)`) or hidden text; fix with `page_ignore`.
- Never lengthen or edit a model `instructions` text casually: it is part of the cache key and a change re-reads every page of that source.
- Names printed over a repeated watermark word come out interleaved with `pdfplumber`; `text_flow: true` keeps drawing order and may separate them (it did not fix Zizzi's section titles).

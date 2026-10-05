# Playbook: onboarding chains without Pearl Scan

Written 2026-10-02 from the first 9 chains (Beefeater, Brewers Fayre, Table Table, Five Guys, Pizza Express, Cineworld, Domino's sides, Vue, Odeon nutrition tables). Later batches have no Pearl Scan CSV to compare with, so this lists what the pipeline checks on its own, the order of work, what each layout needed, the PDF defects met, and what Pearl Scan got wrong (so its files are never treated as perfect). Spec: `pipeline-design.md`. Plan: `superpowers/plans/`.

## 1. What replaces Pearl Scan

| Check | What it catches | Where | Needs |
|---|---|---|---|
| **Fail-loud parsing** | unknown marker, label, column, unreadable cell, number with no name, mark under no column, text between rows | every parser | nothing |
| **Mark accounting** | an allergen mark dropped or double-used: count the `✓`/`▲` glyphs in the PDF and the marks the parser consumed (key legend excluded) | scratch check used for Cineworld; do it for every matrix | nothing |
| **`coverage`** | a data row lost: pages where `pdftotext` shows more number-carrying lines than parsed rows | `python -m pipeline.cli coverage` (numeric_table sources) | nothing |
| **Arithmetic flags** | misread or mistyped figures: kJ vs kcal, saturates > fat, sugars > carbs, Atwater warning, duplicates with different values | `flags` column (`validate.py`) | nothing |
| **Golden rows** | wrong allergen position (the matrix/grid logic) | `golden/<pdf stem>.csv`, 4–8 rows per PDF read off the rendered page | a person looking at the page |
| **Page summary** | which model-read pages to look at first: rows, rows with error flags, empty cells | `python -m pipeline.cli pages --chain KEY` (from the cache, free) | nothing |
| **Second read** | model misreads on vision pages | `python -m pipeline.cli reread --chain KEY --pages 8,16 --dpi 200 [--pdf name]`: one call per page, lists every differing cell (dash style ignored) | LLM quota (~0.3% per page) |
| **Cross-source** | the same product in two regions or PDFs disagreeing | not built; Belfast/ROI Odeon are the first candidates | nothing |
| **Pearl Scan** (when it exists) | everything above, for nutrition and serving size only | `eval` | the CSV |

Rule of thumb: a source is *approved* when (a) it parses without raising, (b) `coverage` is clean, (c) the flags are explained (the PDF's own arithmetic or printed typos, not parser errors), (d) golden rows for every allergen position type pass, and (e) a person has checked markers, disclaimer and columns in `config/chains.yaml`.

## 2. Order of work for a new chain

1. `python -m pipeline.cli manifest` -> `work/manifest.csv`: pages, characters, image-only pages, assigned parser.
2. Look at 2–3 rendered pages (`pdftoppm -r 80`) and the `pdftotext -layout` text. Decide the layout (section 3).
3. Text layer fine -> config only if a parser covers the layout; otherwise extend a parser with an opt-in option. Text layer corrupt (digits missing, `197` printed as `19`) -> `vision_table`.
4. Write the config (unapproved), run `run --chain KEY` against a temp config with approvals on (see `tests/test_cli.py: chains_file`), read the flags and `coverage`.
5. Allergens: add golden rows read off the page images, covering a `may contain` row, an empty row, a merged-cell row.
6. A person approves in `config/chains.yaml`; `run` then writes `outputs/<key>.csv`.
7. Only now, with the layout known, add the next PDF of the same chain. Identical text in two regions is parsed once.

## 3. Layouts met and what handled them

| Layout | Example | Parser and options |
|---|---|---|
| Name + one row of numbers, one table per page | Five Guys | `numeric_table` |
| Several tables per page with column-header blocks, wrapped names | Pizza Express | `numeric_table` + `header`, `wrapped_names`, `titles` |
| Text cell inside the number run (Portion/Piece) | Domino's sides | `text_values` |
| Amount in the name (`BBQ Dip 25g`, `Bacon Bits - 18g`, `22oz Freestyle`) | Domino's, Odeon | `name_amount` |
| Sub-section titles between rows | Odeon | `free_sections` |
| Rows printed over each other (hidden stale row) | Odeon p1 | `text_flow` (+ `invalid_values` for `#N/A`) |
| Running heads above a table header | Domino's | `furniture` |
| Column-number ruler (`4 5 6 7 ...`) | Odeon | skipped automatically |
| Name printed under its figures (Belfast/ROI) | Odeon | `name_below` |
| Product matrix: one band per product between rules, text columns (name, pack size, ingredients, storage) + 18 figure columns | Odeon pre-packed | `product_matrix` (Odeon sources in `config/chains.yaml`) |
| Amount inside brackets or notes (`(Per Portion of 10g)`, `(16oz as served)`, `75cl`) | Odeon | `name_amount` (name stays as printed) |
| Allergen grid, `Y` marks, rotated headers | Whitbread drinks | `whitbread_drinks_grid` |
| Allergen text list per item | Whitbread breakfast | `premier_inn_breakfast` |
| Allergen matrix, marks by column, merged cells, size groups, per-100g items | Cineworld | `allergen_matrix` |
| Corrupt text layer, image pages, one flat table | Vue | `vision_table` (`claude -p`, 150 dpi for small print) |
| Product sheets: variant table + allergen text blocks, image pages | Papa John's | `vision_products`: model returns cells keyed by printed header + allergen text per row; `header_columns` maps headers (an unknown one stops the run); `rules` turn printed row warnings into `May contain`; `pages` lists table pages |
| Allergen matrix page + nutrition page per product group, image pages | Krispy Kreme | `vision_pairs`: the model returns diet cells, ticked header labels and figures per page; `joins` pair the pages' rows in order (`matrix_section`/`nutrition_section`/`matrix_name` regexes, `by_name` for size rows); `tick_labels` maps printed headers (an unknown one stops the run); a row no join uses stops the run |
| Not done yet | Pizza Hut (3 layouts in one PDF), Coffee #1 (vertical blocks, slanted text), Starbucks, Brewhouse/Cookhouse/Top Golf (judgement) | see the roadmap |

## 4. PDF defects found (all handled by failing loudly first, then an option)

- Corrupt embedded font: digits dropped; found because 0-2% of tokens were numbers on image-like pages. Use vision.
- Touching number cells (`1232` `11.1`): poppler merges them; pdfplumber with a 0.5 pt gap splits them (`page_words_fine`).
- Rows printed over each other at identical positions, one of them all `#N/A` (hidden). `text_flow` layers by drawing order.
- Hidden white headings under the visible one (a template remnant): choose the lowest layer.
- Merged cells: one allergen cell spanning several size rows, or two rows (Churros Medium/Large): marks between rows apply to the rows above and below; variants (`Hazelnut` syrup) keep their own marks; reviewed twice.
- Section names printed vertically centred beside their rows; solved by distance partition (`_partition`).
- Notes spanning allergen columns, labels of note-only rows, notes after headings (`*All weights...`).
- Stray `g` after a figure (`2.7g`) printed in the PDF: kept as printed, row flagged.
- Spelling in the PDFs is kept (`Peacan`, `Blackcurrent`). Pearl Scan sometimes corrected it, sometimes added typos.
- Files: soft hyphen in a Pearl Scan file name; 12 Pearl Scan CSVs are Windows-1252, one mixes UTF-8 lines.
- The Odeon PDFs' own data is inconsistent: kJ is 5 x kcal on many drinks (166 rows flagged `kJ/kcal mismatch`), which is the source, not a parser fault. Check the first flagged rows against the page, then accept the pattern.
- Belfast and ROI are not copies of UK: some rows print the name under the figures, notes follow the amount (`454ml *This product is not recommended...`). Never assume two regions parse alike; run each against `coverage`/`eval`.
- Papa John's sheets: a warning printed once (page 4) applies to some rows only (wheat free base: traces of wheat; vegan items: cross contact with milk and egg). Read the intro and warning pages before approving; encode row-specific ones as `rules`, menu-wide ones in `disclaimer`. A review caught the wheat-free case that Pearl Scan could not.
- Vision allergen text is messy: `Sulphites/Sulphur Dioxide`, `Fish (Tuna)`, `Oats (Gluten Free)`, lost commas, trailing colons, qualifiers (`With Gluten Free Oats - Vegan Stuffed Crust Only`). The allergen vocabulary raises on anything it does not know; the first run over a new document lists them all (use a lenient scratch wrapper).
- Cheap discovery pattern for a vision source: run every page once with a header mapping that records unknown headers and allergen texts instead of stopping; the cache keeps every answer, so mapping afterwards costs nothing. Do not edit the `instructions` text afterwards: it is part of the cache key (53 calls, about $4, to redo).
- Odeon pre-packed matrix: figures print their unit (`22g`, `498 kcal`, `171 k cal`) and words (`N/A`, `not declared`, `-`); the parser drops the column's own unit and keeps the words as printed (now valid nutrient words). Cells are vertically centred and paragraphs overrun their rules, so words are assigned to the nearest line of figures unless a band holds exactly one. Belfast/ROI use different column positions from UK (set per source). Group labels (`BOTTLED DRINKS - CORE`, `IMPULSE ICES`) are the only bold text in the name column and are dropped by font (bold) before names are built; the cue was found by comparing fonts with pdfplumber. Pearl Scan drops brands/labels from names and invents serving sizes (250 ml for a 500 ml bottle), so serving size is not compared for these sources.
- Tiny print on a text PDF (Domino's page 2): a model read of the whole page failed, crops at 150 dpi misread about a quarter of the figures. Read the labels with the model and take the figures from the text layer (`figures_from_text`), check the labels with `snap_labels`.
- YAML: unquoted `Yes`/`No` become booleans; quote them.

## 5. What Pearl Scan got wrong (and its conventions)

- Row glued to the wrong group (Cineworld: `Diet Pepsi 200 ml` filed as a size of Tango Orange).
- Rows shifted between repeated tables (Vue popcorn: `(Dublin)` dropped, values of the neighbouring table).
- Stray `g` removed from printed figures; typos added to names (`Rasoberry`, `Cherrv`), others corrected.
- Conventions, not errors: a per-100g-only row written as a 100 g serving; amounts split off names into `servingsize`/`servingsizeunit`; name = group - sub-group - size. We keep what the PDF prints and map in `eval`.
- Odeon names: Pearl Scan dropped bracketed notes and `*` notes from names, moved amounts into the serving size (also from inside brackets), dropped accents (BACARDI for BACARDÍ), and typed several typos (Cherrv, Berrv, Rasoberry, Crispv, `Sig` as `Sia`). `eval` now falls back to a start-of-name match (notes removed) on a row not yet paired, and compares every cell on it; typos and shortened names that still don't pair go to errata.
- Papa John's: decimal commas printed in the PDF (`1,75`) written as `1.75`; the fraction `1/2` turned into the date `01-Feb` or `0.50`; a brand spelling (`SHEESE`) written `CHEESE`; count columns (`Total portions`, `Total pieces`, `Portion size`) filed under different Pearl Scan columns for the same printed header. `eval` takes list-valued mappings for those (`pearlscan:` per source) and checks the cell wherever Pearl Scan has a value.
- Each confirmed mistake is an entry in `config/ground_truth_errata.yaml` with the reason.
- Consequence: where Pearl Scan is the only check, an unexplained mismatch needs a look at the page before either side is changed. In every case so far both explanations existed (the model once, Pearl Scan several times).

## 6. The model route (`claude -p`, `claude-sonnet-5-5`)

- One page image per call, schema-constrained, cached by image + prompt + schema + model (`work/llm/`).
- Papa John's: 65 page reads (3 at a time) cost about $4.5 reported; nutrition matched Pearl Scan on 434 rows and 6,943 cells with 0 mismatches.
- Cost: about 0.4% of a 5-hour plan window per call at default settings (measured 2026-10-02: 5 calls = 2 points); running from an empty directory with `--setting-sources user --strict-mcp-config --disable-slash-commands` gave about $0.05 per call. 14 Vue pages cost roughly 6 points. 140 pages (Papa John's + Krispy Kreme) are about 40-55.
- Accuracy on Vue after review: 3,600 cells, 2 misread at 110 dpi (small print), 0 at 150 dpi. Use 150 dpi for small print.
- Dropped rows on vision pages are only caught by a second read (`reread`) or Pearl Scan; run `pages` first and re-read the pages with error flags or empty cells. Papa John's: 6 flagged pages re-read at 200 dpi agreed with the first read (the flags are the PDF's own inconsistencies); the one difference was an en dash versus a hyphen.
- Never run the model in tests (`tests/conftest.py` blocks it).

## 7. Effort observed (to plan windows)

Config-only chain on an existing parser: 1-3 points. New option on a parser: 3-5 (Odeon UK needed five options, a word-reader change and an evaluator change: about 12 points in total, most of it diagnosing PDF defects). New parser: 6-10 plus a fresh review (3-4 points) for matrix or LLM work. Reviews found real bugs every time (8 on Cineworld, 6 on the backend); keep them.

## 8. Open improvements

1. Automatic row-count check for vision pages (today: `pages` + `reread` by hand).
2. Cross-region checks (Odeon UK/NI/ROI share products).
3. A `--dry-run` cost estimate and CLI-set caps for the model route; concurrency of 3.
4. Mark accounting as a permanent `check` command for matrix sources, not a scratch script.
5. Flags report across all chains (counts by kind) for the final review.

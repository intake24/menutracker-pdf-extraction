# Goal: November 2026 batch (nutrition only)

Status: first round done 2026-11-16 (results: `docs/end-of-round-report-2026-11.md`); the pending list below is open. Same rules and done criteria as `docs/goal-batch-2026-03.md`, with the dates changed; procedure in `docs/runbook-monthly-batch.md`. Results go to `outputs/data-dictionary/findings-report-2026-11.md` and `end-of-round-report-2026-11.md`, with a copy in `docs/`.

## Objective

Parse the nutrition PDFs the research team put in `inputs/collection/` (per-chain folders; no list spreadsheet this month; 75 unique PDFs copied flat into `inputs/`, the folder stays as the source of record), extract the nutrition data per food chain into `outputs/<id>_<Key>.csv`, and verify the results with the pipeline's own checks, the figure-in-page-text check (`tools/figcheck.py`), golden rows and a fresh reviewer. There is no Pearl Scan data.

## Decisions carried over

- No allergen columns (option B). The agent decides `approved: true` and lists every call under "Remarks for the owner". New chains are phase 2.
- Golden files of an earlier PDF with the same name are never overwritten: the source option `golden: <name>__2026-11` names the new file (same-name PDFs every month: Papa John's `nutritional-information`, Cookhouse main and kids menus).
- A source whose document has no PDF this month is deleted from its chain (one unapproved source stops its chain); a chain with no PDF at all stays `approved: false # no November 2026 PDF`.
- Images are converted to one-page PDFs (`<Chain>_<NAME>.pdf`, originals kept) and the conversion is documented in the findings report (the owner agreed in September).
- A source of an earlier issue is recovered from git history (`git show 7bf31f1:config/chains.yaml` is the June config, before the September deletions).

## Starting point

- September 2026: 19 chains with CSVs, 7,994 rows, 30 PDFs plus 5 JPGs; nine chains without a PDF and Five Guys with a PDF that has no nutrition. `docs/end-of-round-report-2026-09.md` has the per-chain state and the doubtful calls.
- Tools: `tools/figcheck.py` (every figure of a model-read PDF on its page), `tools/gcheck.py` (golden file against the PDF text), `tools/cfgedit.py` (rename and drop sources).

## Decisions for November (owner, 2026-11-16)

- The drop has a new shape: `inputs/collection/<id>_<Chain>_Nov-16-2026/` with PDFs and, for about 50 more chains, scraper files (CSV and JSON of the same rows, nutrition per serving, from the chains' web sites: McDonald's, Nando's, Pret, Greggs, KFC, Burger King, Costa, Wagamama and others). **Scraped CSV/JSON files are out of scope** (the pipeline reads PDFs); they are listed in the findings report as "scraped data, not handled by this pipeline".
- **Allergen-only PDFs are skipped** (nutrition only, as since March) and listed in the findings report.
- Flat copy: `inputs/*.pdf` (names unchanged; two identical copies of the Farmhouse Inns / Greene King PDF collapse to one). September `outputs/` moved to `outputs/_2026-09/`; September `inputs` and `outputs` are also archived at `~/dev/menutracker-archive/2026-09/`.

## Intake table (nutrition PDFs; "skip" = allergen or ingredient list only)

| Chain | November file(s) | Compared with September |
|---|---|---|
| `7_Starbucks` | `AUT%2026_UK_AllergenBook_CORE_FOOD_v04`, `AUT_26_..._CORE_BEVERAGE_v04` (autumn), `HOL26_UK_AllergenBook_CORE_FOOD_v03`, `HOL_26_..._CORE_BEVERAGE_v03` (holiday) | new seasonal books (four, not two) |
| `8_Pizzahut` | `DINE-IN_AIN_Booklet_C3_2026_FINAL_V1` | same file as September |
| `9_Subway` | `UKIBuildsandIngredientsNutritionalInformationNovember2026AD` (5 pages); skip `UKallergeninformationC5` | new issue, new name |
| `11_PizzaExpress` | `13294855...` (Nutrition, England/Wales/Scotland), `b2599bdf...` (Nutrition, Northern Ireland), `1bebca8e...` and `a9adac8b...` (Mac & Wings), `4248f3d3...` (QSR Brixton); skip `13fc56df`, `249d05c9`, `54f700af`, `7899ebac`, `981c035b`, `bde1babf` (allergen or ingredient lists) | new hashes; check which Mac & Wings is current |
| `20_ChefBrewer` | 11 menu PDFs (picky bits, drinks, menu, breakfast, sunday, little ones, buffet, no gluten menus) | was 4 sources, unapproved since June |
| `24_Zizzi` | none (scraped CSV/JSON only) | out of scope this month |
| `25_Ask` | `d1613137...` (Autumn 2026 allergen and nutritional information, 51 pages) | was unapproved since September |
| `26_PapaJohns` | `nutritional-information` (79 pages; September had 81) | same name, changed |
| `31_FlamingGrill` | 4 no-gluten menu PDFs with nutrition (Spring Summer 2026 nutritional information) | unapproved since June |
| `35_KrispyKreme` | `UK_Cinnamon_Allergen_Nutrition_Book_041126` (64 pages) | new book (doughnuts) |
| `44_Boswell` | `Nutritional-Values-Food-2024-1`, `Nutritional-Values-Drinks-2024-2`; skip `ALL-ALLERGENS-2026-v2` | new chain |
| `45_Brewhouse` | same August PDF as September | unchanged |
| `46_Cineworld` | `2d0517b6...` (16 pages), `2d377f6b...` (17 pages) | two PDFs; September had one |
| `47_Coffee1` | `C1-Core-Food-Oct-2026-Issue-Date-1910`, `C1-Festive-Food-Beverage-Information-Nov-2026-Issue-Date-0511`, `C1-Core-Beverage-...-April-26-v1` | food returns; festive and beverage sources recovered from git |
| `52_FiveGuys` | `FGUK_FOH_..._MM_shake_DIGITAL_20261013` (1 page) | allergen chart again: check for nutrition, else skip |
| `58_Vue` | `m20744-nutritional-info-food`, `m20744-nutritional-info-drinks`, `m20756-nutritional-info-sweets`, `m20493-nutritional-info-icecream`; skip the five allergen PDFs | food and ice cream return |
| `59_Odeon` | `nutritional-information-november-2026-...-v32`, `pre-packed-product-matrix-november-2026-...-v26`; skip `allergens-matrix-...-v36` | new issues, UK only |
| `6_Dominos` | `nutrition_pizzas`, `nutrition_sides-and-desserts` (7 Sept 2026); skip `allergen_leaflet`, `ingredients-and-allergens` | returns after September |
| `62_Pho` | `Pho-Nutritional-Guidelines-2026_web` (macros); skip `Pho-Allergen-Guide-2026_web` | returns; no kcal keyword hits in the text layer: check |
| `66_SohoCoffee` | `2026-Nutritional-Matrix-Food-V16`, `2026-Nutritional-Matrix-Drinks-V5-Christmas-Drinks`; skip `2026-Allergen-Matrix-V15` | drinks return |
| `69_TescoCafe` | `Christmas+2026+GB+Allergen+Matrix+V1` (no NI matrix this month) | new issue |
| `70_Cornish` | `CB-AB-A4-A-1_Allergen_Book_V48_Proof` (110 energy mentions): check for nutrition | new chain? |
| `73_TopGolf` | `legacy_menu` | same name, changed |
| `76_Wasabi` | `WAS_Nutritional_Guide_210926v3` (version 34, 28 pages) | new issue |
| `79_Tortilla` | `tortilla-nutrition-guide` | new name |
| `85_RealGreek` | `TRG-Allergen-Menu-Spring-26` (dated 30 Sept 2026), `TRG-Deliveroo-...` | changed, unapproved since June |
| `51_FarmhouseInns`, `57_GreeneKing` | one identical 77-page allergen PDF | skip (allergen only) |
| `88_ChickenCottage` | `Allergens-Oct-2026-1-scaled.jpg` (allergen chart) and an empty OCR JSON | no nutrition boards this month: skip |
| About 50 chains (McDonald's, Nando's, Pret, Greggs, KFC, Burger King, Costa, Wagamama, Wetherspoons ...) | scraper CSV and JSON only | out of scope |

## Order of work

1. Phase 1: renamed issues of known documents, simplest first (text-layer chains before model-read chains; see the table in the runbook).
2. Phase 2: new documents and chains (add the key from `~/dev/menutracker/menutracker.ipynb`).
3. End: `run`, `eval`, `coverage`, `flags`, `report`, full tests, fresh reviewer, reports, handoff.

## Limits

- Model backend: the owner may choose headless Claude Code or the API per run (runbook 4b). On the API the cap is $20 per run; a stop writes `interim-report.md` and a re-run resumes. The end-of-round report gets a "Model usage and cost" section from `usage`.

As in March: report model calls per chain; pause before any single chain goes beyond a rerun of all its pages twice; commit after each chain passes. The model quota is a 5-hour window: queue the model-read chains (Papa John's 63 pages, Vue 25, Krispy Kreme 20, Soho 20, Tesco 35) one after another in a background script and keep working on text-layer chains meanwhile.


## Pending list (open at the end of the first round, 2026-11-16; items 1-7 done the same day, see the end-of-round report)

Owner answers of 2026-11-17 (all three former open items are closed):

1. Second Mac & Wings PDF (`a9adac8b...`): another restaurant of Pizza Express (#11). Read as a fifth source (region `UK`, golden `a9adac8b...`); its Buffalo Wings (6) and (12) No Dip rows differ from `1bebca8e...` and are flagged as duplicates with different values (the same name and region); the owner decided on 2026-11-17 to keep both rows with region `UK` and leave the conflict to the research team; it is listed in the end-of-round report's remarks.
2. Cornish Bakery `CB-AB-A4-A-1_Allergen_Book_V48_Proof.pdf` (chain `70_Cornish Bakery`, an allergen matrix with one kcal figure per product): skipped by the owner; listed in `config/skipped_pdfs.yaml`.
3. Coffee #1 Ham & Cheese Toastie (October core guide, page 24 into 25): read with the new `join_next_page: {24: 25}` option of `product_blocks` (Salt 1.40/2.80, weight 215 g); `tests/test_product_blocks.py::test_join_next_page_*`; figcheck 0 misses.
4. Optional: a by-eye check of the new goldens against rendered pages. A fresh reviewer checked the open-items parser changes (no regressions on other sources; six findings fixed: `name_beside_middle_row` fills one row only, `serving_column` needs a line without a size word, `carry_labels` is a page list, `block_section` heading rejoin, `bold_font` reset). Still unreviewed: the earlier first-round changes (`numeric_table` `name_below` and `block_section`, `product_blocks` `split_blocks`/`footer_y`/`weight_labels`, `grouped_table` options, `drink_tables` `bold_font`, `vision_products` `name_beside_middle_row`, `llm.py`).

Fresh review of the first-round changes (2026-11-17, Opus subagent; old and new parsers compared on every numeric_table, drink_tables and product_blocks source: sources without new options give identical output). Fixed: sdk answers that were billed but failed (cut off, refused, not JSON) are now added to the spend cap and the usage log; a plain-JSON answer (free-form schemas: vision_products, or the "too complex" fallback) is checked against the schema before it is cached (a number where a string is expected used to crash the parser on every re-run); the interim report lists only the chains written by that run; the usage table folds crop and strip images into their PDF and says headless token counts are partial; docstrings of `name_below`, `title_min_size` and `join_next_page`; `autogolden --n 1`. Also fixed (owner, 2026-11-17): a `grouped_table` data line with a cell printed "-" or "n/a" now stops the run instead of being skipped (checked on the November Boswells PDF: 110 data lines, 110 rows, none short). Still accepted: an empty size (`''` in `own_group_sizes`) for a row whose size word is missing or misplaced. Known and accepted: with 8 parallel API workers the spend cap can be overshot by up to about 7 calls in flight; `join_next_page` keeps small-type words under the footer at any x (nothing else is printed there in the October guide); `tools/autotitles.py` adds titles to every one-line `titles:` list and misses a title containing an apostrophe.

Done in the open-items round: Pizza Express England and Northern Ireland, Domino's, Boswells drinks, Pho, Coffee #1 (April beverages, Festive beverages and savoury page), Starbucks syrup and cold-foam pages.

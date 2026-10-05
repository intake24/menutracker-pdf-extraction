# Chain mapping reference: how each chain's PDFs map to the CSV columns

Written 2026-10-05 after the eleventh chain (Krispy Kreme). It is the record of what each source means in the CSV and which decisions were taken, so that the next collection round (no Pearl Scan data) can follow the same strategy. Read it with `docs/findings-report-2026-10.md` (what went wrong and how it was found), `docs/playbook-new-batches.md` (how to onboard a chain) and `config/chains.yaml` (the settings themselves, with comments).

## 1. Rules that hold for every chain

- One CSV per chain, `outputs/<id>_<Key>.csv`, one row per food, drink or product (per size or variant where the PDF prints one row per size or variant). Column order and the allowed columns are in `schemas/columns.yaml`; a chain CSV holds only the columns that have a value.
- Values are copied exactly as printed (`<0.5`, `Trace`, `171k cal`, `1/2`, typos such as `Peacan`). Problems are shown in the `flags` column (`error:` or `warn:`) and never fixed in the value.
- Allergen cells: `Yes` (printed as present), `May contain`, `No` only where the PDF says that an unmarked cell means absent, blank where the PDF does not say (not stated). Each source sets this with its `markers` setting: see section 3.
- Provenance columns on every row: `region`, `source_file`, `source_page`, `method` (`parser` or `llm`), `flags`.
- An unknown marker, label, column header or diet word stops the run with a message. A new layout is noticed, never guessed.
- A source reaches `outputs/` only with `approved: true` in `config/chains.yaml`, set by a person after reading the flags and checking golden rows.

## 2. Which parser reads which layout

| Parser | Text layer | Layout | Chains |
|---|---|---|---|
| `numeric_table` | yes | name followed by a run of numbers; many options (`header`, `wrapped_names`, `titles`, `text_values`, `furniture`, `name_amount`, `text_flow`, `free_sections`, `invalid_values`, `name_below`) | Pizza Express, Five Guys, Domino's sides, Odeon nutrition |
| `premier_inn_breakfast` | yes | allergen text list per item | Beefeater, Brewers Fayre, Table Table (breakfast) |
| `whitbread_drinks_grid` | yes | allergen grid with `Y` marks and rotated headers | the same three chains (drinks) |
| `allergen_matrix` | yes | marks by column, merged cells, size groups, per-100g items | Cineworld |
| `product_matrix` | yes | one band per product between rules | Odeon pre-packed |
| `grouped_table` | yes | nested labels (pizza, cheese, crust, size) by position | Domino's pizzas |
| `vision_table` | corrupt | one flat table per page, read by the model | Vue |
| `vision_products` | none or tiny print | product sheets: variant table plus allergen text; the model reads labels, figures from the text layer where one exists | Papa John's, Domino's page 2 |
| `portion_tables` | yes | nutrition tables of several widths on a page, product title over size rows | Pizza Hut (pages 17-24) |
| `mark_table` | yes | dish rows with Yes/No diet cells and a circle mark under each allergen, rotated header | Pizza Hut (pages 2-6) |
| `product_blocks` | yes | one block per product: name, ingredient declaration with bold-capital allergens, nutrition column | Coffee #1 food |
| `drink_tables` | yes | drink tables: name and allergens once beside size rows, 9 figures per group, rotated titles | Coffee #1 beverages |
| `guide_rows` | yes | name, declaration, figures and a summary column of allergens per row (rows between rules), size lines for drinks | Starbucks food and drinks |
| `modifier_matrix` | yes | calories and a drawn tick under each rotated allergen label | Starbucks modifiers |
| `vision_pairs` | none | an allergen matrix page and a nutrition page for the same products, joined row by row | Krispy Kreme |

Model reads use `claude -p --model claude-sonnet-5-5`, cached under `work/llm/` by image, prompt, schema and model, so a re-run costs nothing. Check a model-read source with `pages` (rows, flags, empty cells per page) and `reread` (a second read at a higher dpi; any difference means one read is wrong).

## 3. Per chain

Row counts are those of `outputs/` on 2026-10-05 (6,752 in total, before Starbucks).

| Chain | PDFs and regions | Rows | Allergen cells | What to know when reading the CSV |
|---|---|---|---|---|
| 11 Pizza Express | UK and Northern Ireland nutrition menus | 818 | none (nutrition only) | Wrapped names are joined; `Breakfast (selected restaurants only)` is a title. UK and NI rows repeat products with their own region. |
| 16 Beefeater, 17 Brewers Fayre, 21 Table Table | breakfast and drinks menus each (6 PDFs) | 207 each | breakfast: unmarked = `No`; drinks: `Y` = `Yes`, unmarked = `No` (the guides declare intentionally added allergens only) | Drinks rows carry size and milk type; spelt and kamut have no column in the drinks grid, so they stay blank (not `No`). |
| 52 Five Guys | one nutrition table | 54 | none | Plain `numeric_table`. |
| 46 Cineworld | one allergen and nutrition matrix | 284 | `✓` = `Yes`, `▲` = `May contain`, blank = blank (the key says nothing about blanks) | Size groups (Large, Regular, ...) become one row per size; names printed once beside several size rows are repeated; per-100g items give per-100g columns only; a sub-section heading with a hidden second heading uses the lowest layer; calories only (no other nutrients). |
| 6 Domino's | sides and dips (UK), pizzas PDF in four sources | 1,504 | none | Pizza rows are one per pizza, cheese, crust and size; the duplicate check uses cheese, crust and serving size too. Page 2 is read by the model for labels and from the text layer for figures, because a model misread about 23% of small-print figures. `Delight Vegi Small` prints placeholder figures (97 to 106) and stays flagged. |
| 58 Vue | three PDFs (ice cream, food, sweets) | 349 | none printed | Text layer is corrupt (a font drops digits), so the model reads page images at 150 dpi. Items with several size rows give one row per size. |
| 59 Odeon | nutrition tables and pre-packed matrices, each for UK, Belfast (NI) and ROI | 1,299 | pre-packed matrix: as the matrix key | Odeon prints kJ as five times kcal on many rows (flagged, the PDF's own). Belfast and ROI print the name below its figures (`name_below`). Pre-packed rows carry pack size, ingredients and storage. |
| 26 Papa John's | one product-sheet PDF read by the model | 435 | `markers: {"": "No"}` because sheets list every ingredient allergen; printed warnings are `rules` (wheat free base: wheat and gluten `May contain`; vegan items: cross contact) | One row per pizza, cheese, crust and size; stuffed crusts use the "original or authentic thin crust" allergen block because the sheets print no other. |
| 35 Krispy Kreme | one 61-page book, image pages | 210 | `✓` = `Yes`, blank = blank; diet cells `Suitable_for_Vegetarian`, `Suitable_for_Vegan`, `Suitable_for_Halal` hold YES or NO as printed | The allergen page and the nutrition page of a group are joined by page order and section; names that differ a little are flagged (the nutrition page's name is kept). `Category` keeps the printed section, which for drinks names the milk (`HOT DRINKS – OAT MILK`). Delivery boxes, gifting dozens and syrups have allergens and diet cells but no figures (the PDF prints none). Ingredient-declaration pages are not extracted. |
| 8 Pizza Hut | one booklet: allergen tables, nutrition tables (ingredient prose pages not extracted) | 715 (after `merge_by_key`) | filled circle = `Yes`, empty circle = `May contain` (the key: a risk of cross-contamination), blank = blank; diet cells `Suitable_for_Vegetarian`, `Suitable_for_Vegan`, `Suitable_for_Coeliac` hold Yes/No as printed; "Fish / shellfish" sets fish and crustacean | Pizza rows are one per pizza and size (`Size` is the crust and size line), per-slice figures in the `Per Slice` columns with `Total_Weight` and `Total_Slices`; other tables per portion; `Category` keeps headings as printed (nested headings joined with ` - `); "<20ppm" marks are kept in `notes`; an allergen row and a nutrition row are merged only when very likely the same product (same name, size, region, heading up to punctuation or depth, one partner each way): `source_page` then reads "17, 2" and `notes` starts a "Merged product: ..." remark; similar names that may be different products stay separate rows. |
| 47 Coffee #1 | food guide (18 pp) and beverage guide (28 pp) | 463 | food: bold capital words of the declaration = `Yes`, capital words after "May contain" / "Made in a factory that handles" = `May contain`; drinks: the allergen column; an unnamed allergen is `No` (both guides say every allergen is listed); `OAT` in drinks and "Gluten Free OATS" in food set `oats` only | Food: `Category` is the section title as printed ("PASTIRES"), `Diet` the printed tag, `Ingredients` the declaration, `notes` a note printed under a section (porridge milk); figures per 100 g and per portion, `Serving_Size` the portion weight. Drinks: `Product_Name` is the printed name ("Latte - Whole Milk"), `Size` the printed size (Regular, Large, 12oz), `Product_Description` the line under the table title; syrups are one row per portion (15 ml, 22.5 ml); vitamin C and B12 content are per portion. |
| 7 Starbucks | food guide (93 rows), beverage guide (1,426 rows) and its Modifiers pages (38 rows) | 1,557 | the summary column of allergens (the bold capitals of the declaration are read as a check and differences are flagged); an unnamed allergen is `No`; "gluten free OATS" sets oats only; a tick under a gluten cereal on the Modifiers pages sets gluten too | Food: `Suitable_for_Vegetarian` / `Suitable_for_Vegan` hold Y or N as printed, `Category` is the menu and section bar. Drinks: `Size` is the printed size (Tall, Grande, Venti, Single, Doppio, ...), figures are per drink size (`Per Portion`) with `caffeine`; `Ingredients` is the declaration. Modifiers: calories only, `Size` is how it is served ("Espresso Beverage per pump", "per serving"). |

## 4. Decisions and how they are encoded

| Question | Decision | Where |
|---|---|---|
| Blank allergen cell | Not stated (blank) unless the key says unmarked means absent | `markers` per source |
| Gluten | Never derived; `gluten` is set only where the PDF prints it (cereal columns are `wheat`, `rye`, `barley`, `oats`) | `labels` or `tick_labels` per source |
| A warning that applies to some rows only (traces, cross contact) | Encoded as a rule so the row carries `May contain` | `rules` (Papa John's) |
| Diet cells (vegetarian, vegan, halal) | Kept as printed (YES/NO) in `Suitable_for_*` columns | `schemas/columns.yaml`, `vision_pairs` |
| Serving size | Compared with Pearl Scan only where it prints it; Pearl Scan invented sizes (250 ml for a 500 ml bottle) | `pearlscan:` overrides |
| Pearl Scan mistakes | Recorded with the reason in `config/ground_truth_errata.yaml` (66 entries); never copied into outputs | errata file, `name_fixes` for renamed items |
| Duplicates | Same name, category, cheese, crust, size, serving size, milk and region with different values is an error; identical values are not | `pipeline/validate.py` |
| Rows the PDF lists without figures | Kept with the cells the PDF does give | `vision_pairs` matrix-only joins |

## 5. Using this without Pearl Scan data

1. Run `manifest`, look at two or three rendered pages, choose the parser (section 2). Layout match: config only. Close match: add an opt-in option and a test. No match: a new parser, with its own tests and a fresh review.
2. Read the PDF's introduction and key pages for what a blank cell means, then set `markers`.
3. Run with a temporary approved copy of the config (see `tests/test_cli.py`) and read every flag, then `coverage` (text layers) or `pages` (model reads).
4. Allergens: write golden rows by reading the rendered page for a few products that cover a may-contain row, an empty row and a merged or unusual row; for model reads add `reread` at a higher dpi on every page that carries allergens.
5. Figures without Pearl Scan: arithmetic flags (kJ against kcal, saturates against fat, sugars against carbohydrate), the second read, and a second look at the pages with the most flags or empty cells.
6. Review by a fresh model (Opus) for every new parser and for any slice that touches allergens or the model route; fix findings with tests that fail first.
7. A person approves in `config/chains.yaml`; `run`, `eval`, commit.

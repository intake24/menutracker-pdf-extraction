# Findings report: PDFs, Pearl Scan, and the pipeline (first round, October 2026)

Status date 2026-10-02. This report records what was found when every extracted source was checked three ways: against the PDF page, against Pearl Scan's CSV, and against the pipeline's own output. It lists the errors found in each source, who was wrong (the PDF, Pearl Scan, the model, or the pipeline), a verdict for each source, and what to do differently in later batches. Companion documents: `playbook-new-batches.md` (how to onboard a chain), `pipeline-design.md` (the spec), `ground_truth_errata.yaml` in `config/` (every Pearl Scan mistake with its reason).

## 1. Summary

| Chain | Sources | Rows out | Check against Pearl Scan | Pipeline faults found | Verdict |
|---|---|---|---|---|---|
| Beefeater, Brewers Fayre, Table Table | 6 PDFs (breakfast text lists, drinks grid) | 207 each | golden allergen rows (no nutrition truth for the grid) | 2 critical + 8 important (review) | Approved; allergens rest on golden rows |
| Five Guys | 1 | 54 | 972 cells, 0 mismatches | 0 | Approved; 4 rows carry the PDF's own arithmetic flags |
| Pizza Express (UK, NI) | 2 | 818 | 8,154 + 6,570 cells, 0 mismatches | 1 critical + 5 important (review) | Approved |
| Cineworld | 1 | 284 | 225 rows, 633 cells, 0 mismatches; 8 golden allergen rows | 8 findings (review) | Approved |
| Domino's sides and dips | 1 of 2 | 82 | 82 rows, 2,788 cells, 0 mismatches | 0 | Approved; pizzas PDF (1,422 rows) not done |
| Vue | 3 (image text) | 349 | 342 rows, 0 mismatches after 9 errata | model misread 2 digits at 110 dpi | Approved |
| Odeon nutrition tables (UK, Belfast, ROI) | 3 | 1,013 | 705 + 147 + 148 rows, 0 mismatches after errata | 0 after fixes | Approved |
| Odeon pre-packed matrices (UK, Belfast, ROI) | 3 | 286 | 97 + 82 + 79 rows, 0 mismatches after 33 errata | name glue (fixed) | Approved |
| Papa John's | 1 (image pages) | 435 | 434 rows, 6,943 cells, 0 mismatches after 7 errata | 1 critical + 4 important (review) | Approved |
| Krispy Kreme, Domino's pizzas, Pizza Hut, Coffee #1, Starbucks, Brewhouse, Cookhouse, Top Golf | not done | | | | Surveyed or not started, see section 4 |

Totals in `outputs/`: 10 chain CSVs, 3,942 rows. Pearl Scan agreement is exact on every compared cell once the 63 confirmed Pearl Scan mistakes are excused. Allergen data has no ground truth anywhere; it is checked by hand-verified golden rows only.

## 2. How the checks worked and who decides

1. **PDF page (rendered image or text layer)** is the authority. Where Pearl Scan and the pipeline differ, look at the page.
2. **Pearl Scan CSV** is a reference for nutrition and serving size only. It has no allergen columns for these PDFs.
3. **Pipeline output** is checked by fail-loud parsing, arithmetic flags, golden rows, and (new) `coverage`, `pages` and `reread`.

Every mismatch was settled by looking at the page. In every case so far one of four things explained it: the PDF itself is odd (kept as printed and flagged), Pearl Scan changed or mistyped the value (errata), the model misread (re-read at higher resolution), or the pipeline had a defect (fixed with a test). Over the round the counts were:

| Cause | Count found | Example |
|---|---|---|
| PDF prints something odd; we keep it and flag it | many (hundreds of flagged rows) | kJ printed as 5 x kcal on Odeon drinks; `1,75` with a decimal comma; `2.7g` with a stray unit |
| Pearl Scan mistake or convention (errata or `eval` rule) | 63 errata entries plus 6 evaluator rules | `Diet Pepsi` filed under the wrong item; `1/2` turned into the date `01-Feb` |
| Model misread (vision) | 2 cells in about 3,600 (Vue, 110 dpi) | `1.4` read as `0.4`; fixed at 150 dpi |
| Pipeline defect | about 40 found by reviews and checks | marks landing in the wrong column; a wheat-free row marked gluten "No" |

## 3. Findings per source

### 3.1 Whitbread chains: Beefeater, Brewers Fayre, Table Table (6 PDFs)
- **PDFs:** the breakfast list is a text document (Contains / May contain per item). The drinks guide is a grid with rotated header labels and `Y` marks; sections are centred headings. Identical text across the three chains, so one parser serves all.
- **PDF oddities:** spelt and kamut have no column in the grid (left blank, not "No"). Some headings say "see packaging label for allergens" (a complete but empty section). The drinks guide "declares intentionally added allergens only" and prints no "may contains", so an unmarked cell is "No" by its own key.
- **Pearl Scan:** no truth for these (they are allergen documents). The only reference was human-checked golden rows, and **the first golden file had many products missing** (the user found this by checking the Brewers Fayre drinks file against the PDF).
- **Pipeline faults (review, 2 critical + 8 important):** drifted marks landed in neighbouring columns; sub-point y offsets turned a `Y` into a heading; label words in the body dropped rows; unparsed allergen text was dropped silently. All fixed with tests.
- **Verdict:** trustworthy for the layouts seen; an allergen error here means a wrong mark, so spot-check new drinks guides.

### 3.2 Five Guys (1 PDF, numeric table)
- **PDF oddities:** the PDF's own figures fail the arithmetic checks on 4 rows (saturates > fat, sugars > carbs, kJ/kcal). Kept as printed and flagged.
- **Pearl Scan:** agreed on all 972 cells.
- **Pipeline faults:** none after Phase 2a review (silent mis-columns, unreadable cells leaking into names, lost wrapped names, a parse cache that ignored the column list: all fixed).
- **Verdict:** approved.

### 3.3 Pizza Express UK and Northern Ireland (2 PDFs)
- **PDF oddities:** several tables per page, wrapped names, a title (`Breakfast (selected restaurants only)`) printed once and applying to the sections after it; 34 rows flagged by the PDF's own arithmetic.
- **Pearl Scan:** agreed on 8,154 and 6,570 cells and on every section name.
- **Pipeline faults (1 critical + 5 important):** wrapped names glued a line with numbers onto the next name; a product called "Energy Bar" was read as a header; names with swallowed number runs were accepted; `page_words_fine` could replace one number with another on slanted text; stray text above a header became a persistent parent. All fixed.
- **Verdict:** approved.

### 3.4 Cineworld (1 PDF, allergen matrix with marks)
- **PDF oddities (many):** three sub-layouts in one table (size groups, per-100g items, items with no amount); names printed once, vertically centred beside several size rows; marks in cells merged across rows or between two rows; note rows spanning the allergen columns; section headings with a second, hidden heading printed in white under the visible one; `Peacan` and `Blackcurrent` spelt as printed; key declares only "contains" and "may contain" (a blank is "not stated").
- **Pearl Scan:** 225 rows matched (kcal and serving only). It had filed `Diet Pepsi, 200 ml` as a size of Tango Orange Sugar Free (the PDF lists it as its own item) and wrote per-100g rows as 100 g servings.
- **Pipeline faults (review, 8 findings, none visible to Pearl Scan):** variant rows (`Semi-Skimmed Milk`, `Soya Milk`) shared each other's allergens; a mark merged across `Churros Medium / Large` landed on one row only; headings with `&` or a star note were missed or turned into products (2 fake rows); sub-section labels crossed heading boundaries; evaluator rules could mask real mismatches.
- **Verdict:** approved. The review found five bugs that no ground-truth comparison could have caught, because Pearl Scan has no allergen data. Every mark in the PDF (260 contains, 175 may contain, plus the key legends) is accounted for.

### 3.5 Domino's sides and dips (1 of 2 PDFs)
- **PDF oddities:** three blocks of ten values (per 100g, per product as sold, per portion) with a word cell and a serves cell in the middle of the row; names with amounts (`BBQ Dip 25g`); a running head above the table; 3 rows flagged by the PDF's arithmetic.
- **Pearl Scan:** 82 rows and 2,788 cells agree; it moves the amount into the serving size (we do the same through `name_amount`).
- **Verdict:** approved. The pizzas PDF is not done (3 nested merged columns, 1,422 rows).

### 3.6 Vue (3 PDFs read from images)
- **PDF oddities:** the embedded font drops digits (`197` printed as `19`), so the text layer cannot be used; the first digit of some cells is missing in the text but present in the image. The PDF prints `0g`, `2.7g`, `1133g`, `14g` and `6.8g` with a stray `g`. The ice-cream table prints the portion `1 Scoop Tub` on a second line.
- **Pearl Scan errors (9 errata):** stray `g` removed from 6 cells; the popcorn tables (one is `Salted Popcorn (Dublin)`) had their `(Dublin)` dropped and values shifted between tables, so three row names pair with the wrong table.
- **Model:** at 110 dpi the model misread two digits in the small print (`1.4` as `0.4`, `0.4` as `0`), found because Pearl Scan disagreed; at 150 dpi it was exact on all 3,600 cells compared. Everything else the model returned was faithful, including the stray `g` and the PDF's own wrong figures.
- **Verdict:** approved. The vision route is accurate at 150 dpi, but without Pearl Scan the two misreads would not have been caught (see lessons 5 and 6).

### 3.7 Odeon nutrition tables (3 PDFs: UK, Belfast, ROI)
- **PDF oddities (many):** rows printed over each other at identical positions (a hidden `Onions - 142g` row with `#N/A` under `Guacamole`); sub-section titles between rows; a column-number ruler line; amounts in names in five spellings (`- 18g`, `75cl`, `(16oz as served)`, `454ml *This product is not...`); in Belfast and ROI some names are printed *under* their figures; the PDF's kJ is 5 x kcal on many drinks (166 UK rows flagged); Belfast and ROI have identical text but are not copies of UK.
- **Pearl Scan errors (13 whole-row errata plus conventions):** typos it introduced (`Cherrv`, `Berrv`, `Rasoberry`, `Crispv`, `Sig` as `Sia`), inconsistent names for the 25 ml and 50 ml gin rows, dropped accents (`BACARDI` for `BACARDÍ`), notes and amounts removed from names. The evaluator now ignores accents, trademark signs and bracketed notes in names and falls back to a start-of-name match, always comparing every cell.
- **Pipeline faults:** none left; the diagnosis added `text_flow`, `free_sections`, `invalid_values`, `name_below` and bracketed amounts.
- **Verdict:** approved; UK 705 rows, Belfast 147 and ROI 148 agree on every cell.

### 3.8 Odeon pre-packed matrices (3 PDFs)
- **PDF oddities:** one band per product but cells are vertically centred and paragraphs overrun their rules; figures print their unit (`22g`, `498 kcal`, `171 k cal`) and words (`N/A`, `NA`, `-`, `not declared`); typos (`<0/1`, `<0,005`); serving sizes that are counts (`8 sweets`); bold group labels (`BOTTLED DRINKS - CORE`) sit in the name column; Belfast and ROI use different column positions from UK; one row prints 14 figures instead of 18.
- **Pearl Scan errors (28 whole-row and 5 cell errata):** `Popcom`, `Im Bru`, `Cometto`, dropped brands (`Aero`, `Oreo`, `Ben &`), `Cadbury Egg` for `Cadbury Creme Egg`, a missing `C` in `Caramel`; it invented serving sizes (250 ml for a 500 ml bottle) and left counts blank; it kept `171k cal` with the stray space and changed `<0,005` to `<0.005`. Serving size is therefore not compared.
- **Pipeline faults:** group labels glued into names (found by comparing with Pearl Scan, fixed by font: labels are the only bold text in the name column); a numbers-only check misfiled prose notes in the figure area; first column guesses were off.
- **Verdict:** approved. Ingredient text is as printed, allergens in bold are not derived (no allergen column in the PDF).

### 3.9 Papa John's (1 PDF, 79 image pages, product sheets)
- **PDF oddities:** no text layer; each sheet has a variant table (crust x size), two figure blocks, allergen text per dough or base, and a warning on page 4 that applies to some rows only (wheat free base: traces of wheat; vegan items: cross contact with milk, egg and meat; pizzas without cheese may have traces of milk). Decimal commas printed (`1,75`, `8,6`); `Sheese` is the vegan brand's spelling; two count headers (`TOTAL PORTION SIZE`, `TOTAL IN BOX`) appear to mean the same.
- **Pearl Scan errors (7 errata):** `1/2` turned into the date `01-Feb` (3 rows) or `0.50`; the two decimal commas changed; `Sheese` written `Cheese`; counts filed under `total_pieces` for some products and `total_portions` for others. The evaluator takes list-valued mappings for these count columns.
- **Pipeline faults (review, 1 critical + 4 important):** the wheat-free rows came out gluten "No" and wheat "No" although page 4 warns of wheat traces (the golden row had locked that in); `Total_Portions` mixed pieces and portions; a qualified allergen (`With Gluten Free Oats - Vegan Stuffed Crust Only`) could be dropped silently; two budgets together allowed double the cap.
- **Model:** 65 page reads, three at a time, about $4.5 reported; first read matched Pearl Scan on all 434 rows; 6 flagged pages re-read at 200 dpi agreed (the flags are the PDF's own inconsistencies; the only difference was an en dash).
- **Verdict:** approved with two stated judgements: stuffed crust rows use the "original or authentic thin crust base" allergen block because the sheets print no other; row-specific warnings are encoded as `rules`.

## 4. Sources not done: what was learned

| Source | PDF | Why not done yet | What the survey found |
|---|---|---|---|
| Krispy Kreme | 61 pages, no text layer | needs a join of two page types | page pairs: an allergen matrix page (dietary YES/NO and ticks in 25 columns) then a nutrition page; plus ingredient-declaration text pages and beverage pages. One CSV row per product needs the two joined by name, which the pipeline cannot do yet. |
| Domino's pizzas | 18 pages, 1,422 GT rows | parser written, pages 3-13 only | `grouped_table` reads pizza, sideways cheese label and crust labels by position and size order; pages 3-13 give 1,148 rows, all cells agree with Pearl Scan (recall 80.6%, one Pearl Scan figure wrong: 6.7 for the PDF's 5.7). Page 2 (rows sorted by size across pizzas, then trios), bases, sauces/cheese and the three toppings pages (per-100g row plus four size rows per topping) still need sources; two pizzas ('Absolute Banger', trial-stores pizzas) are missing from pages 3-13's output. |
| Pizza Hut | 24 pages, 483 GT rows | three layouts in one PDF | allergen tables with Yes/No and `●`/`○`, ingredient prose, per-slice nutrition tables |
| Coffee #1 | food 18 pp (vertical blocks), drinks 28 pp (slanted text) | slanted text defeats the word reader | vision route likely for the drinks |
| Starbucks | food 20 pp, drinks 73 pp | not started | wrapped names, size rows, milk type in the product line |
| Brewhouse, Cookhouse, Top Golf | menus | judgement | dish name is the text before the first comma |

## 5. Errors in Pearl Scan, by kind (so they are recognised next time)

| Kind | Examples | Handling |
|---|---|---|
| Typed errors in names | `Popcom`, `Cherrv`, `Berrv`, `Rasoberry`, `Crispv`, `Sia`, `Cometto`, `Im Bru` | errata (`*` for the row) |
| Brand or note dropped from names | `Aero Bubbles` as `Bubbles`; `(Per Portion of 10g)` removed | evaluator start-of-name fallback; errata where it still fails |
| Values changed | `1,75` to `1.75`; `<0,005` to `<0.005`; stray `g` removed; `1/2` to `01-Feb` or `0.50` | cell errata; we keep the printed value and flag it |
| Row filed under the wrong item | `Diet Pepsi 200 ml` as a size of Tango Orange | row errata |
| Rows shifted between repeated tables | Vue popcorn, `(Dublin)` dropped | row errata |
| Invented values | serving size 250 ml for a 500 ml bottle; counts under a different column for the same printed header | serving size not compared; list-valued column mappings |
| Dropped characters | accents (`BACARDI`), `™` | evaluator ignores both |
| Conventions, not errors | per-100g row written as a 100 g serving; amount moved from name into serving size; name = group - sub-group - size | `eval` rules; we keep what the PDF prints |

Rule applied throughout: Pearl Scan is a useful second reader, not the authority. Pearl Scan was wrong in a large share of the discrepancies (63 confirmed entries). We never changed our value to match Pearl Scan without reading the page.

## 6. Errors by the pipeline (found by review and by comparison) and their fixes

| Slice | Review result | Typical defect |
|---|---|---|
| Phase 1 (Whitbread) | 2 critical, 8 important | marks in neighbouring columns; sub-point y offsets; unparsed allergen text dropped |
| Phase 2a (numeric tables) | 5 important | silent mis-columns; cache ignored columns; unapproved chains made default runs fail |
| Phase 2b (Pizza Express) | 1 critical, 5 important | wrapped names glued; header misdetected; cache ignored options |
| Cineworld matrix | 8 findings | variant rows sharing marks; merged cells landing on one row; headings with symbols |
| LLM backend | 6 important | invalid answers cached; non-atomic cache; stderr rate limit missed; env leaked |
| Papa John's | 1 critical, 4 important | wheat-free allergens "No"; mixed count columns; silent qualifier drop |
| Direct checks (no review) | about 12 | pizza lookup soft hyphen; mixed-encoding CSV; group labels in names; count of marks |

A review by a fresh reader found a real defect in every slice where we asked for one. The most serious ones, the Cineworld and Papa John's allergen errors, could never have shown up in a comparison with Pearl Scan, which has no allergen data.

## 7. Lessons and mitigations for the next batches

1. **Treat allergens as unverified until a person has looked.** Pearl Scan has none, so matching it proves nothing for allergens. Require golden rows covering a may-contain row, an empty row, a merged-cell row, and a row affected by a printed warning on another page. Read every introduction and warning page of every PDF before approving (Papa John's page 4).
2. **Fail loudly first, then add an option.** Every parser raised on unknown markers, labels, headers and cells; each raise was a real layout feature we had not met (overlaid rows, name under figures, `#N/A`, notes in the figure area). Never loosen a raise to a default.
3. **Count rows independently.** `python -m pipeline.cli coverage` (text-layer sources) and `pages` (model-read sources) need no ground truth. Run them before approval; investigate any page short of rows.
4. **Account for every mark and every token.** Count the glyphs in the PDF and the ones consumed (Cineworld: 260 + 175); a difference is a lost mark.
5. **Re-read doubtful vision pages.** `reread --dpi 200` costs about 0.3% of a window per page. Use 150 dpi from the start for small print. Run `pages` first to choose pages with error flags or empty cells.
6. **Do not edit instructions text after a vision run.** It is part of the cache key; changing it re-spends the whole run (about $4). Put notes in comments. Use the discovery pattern: first pass with lenient scratch wrappers to collect every unknown header and allergen phrase, then add the mappings; the cache makes the second pass free.
7. **One review per slice that touches allergens or the model route.** It found real defects each time.
8. **Never loosen the evaluator without a test that a real mismatch still fails.** Each rule added this round (accents, trademarks, start-of-name match, per-100g, list-valued counts) came with such a test, and a review looked for masking.
9. **Region PDFs are not copies.** Belfast and ROI differed from UK in layout and column positions; run each against `coverage` and a golden check.
10. **Record every confirmed Pearl Scan mistake with its reason** (`ground_truth_errata.yaml`), so the same error is not rediscovered and so a future reader can see why a value differs.
11. **Guard against my own workflow errors:** a failing test once slipped into a commit because a pipe hid its exit code, and one `rm -rf outputs` removed your sample files (restored from version history). Rules now: tests are run on their own, never behind a pipe in a chain; data folders are never deleted.
12. **Quota planning:** a config-only chain costs 1-3 points of a window, a new parser option 3-5, a new parser 6-10, plus a review of 3-4. A 65-page vision read is about 15-25 points. Plan about two windows for the remaining list.

## 8. Known limits (what a user of the CSVs should know)

- Allergen cells are "Yes", "May contain", "No" (only where the PDF declares absence) or blank (not stated).
- Values are exactly as printed, including decimal commas, stray units and the PDF's own arithmetic errors; the `flags` column records them. About 16% of Odeon rows carry error flags (212 of 1,299), almost all from the PDF itself.
- Model-read sources (Vue, Papa John's) depend on a model reading small print; two misreads in 3,600 cells at the wrong resolution show the risk. There is no automatic row-count check on those pages yet; use `pages` and `reread`.
- Ingredients text is as printed; bold allergens inside it are not parsed into allergen columns.
- Serving sizes of Odeon pre-packed products are as printed; Pearl Scan's invented ones are not reproduced.

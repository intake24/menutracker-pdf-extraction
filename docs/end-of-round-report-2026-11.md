# End-of-round report: November 2026 batch

Written 2026-11-16. Goal: `docs/goal-batch-2026-11.md`. Nutrition only, no Pearl Scan. The batch was also the **first run on the Anthropic API** (Sonnet 5.5) and was restarted once to measure its cost (figures kept locally): the four chains finished before the restart (Subway, Tortilla, Wasabi, Odeon) were set aside (`outputs/_discarded-2026-11-restart/`) and re-extracted, and the usage ledger was reset.

## Result

- 23 chains produced a CSV, 12,942 rows (the first round had 21 chains and 9,754 rows; Domino's and Pho and more rows for Starbucks, Boswells, Pizza Express and Coffee #1 came from the open-items round, see below), from the November collection in `inputs/collection/` (75 unique PDFs; 21 chains read). `eval` passes for every source, `coverage` and the full suite pass (342 tests).
- 7_Starbucks: 3,706
- 59_Odeon: 813
- 58_Vue: 701
- 20_ChefBrewer: 533
- 26_PapaJohns: 483
- 25_Ask: 382
- 69_TescoCafe: 372
- 46_Cineworld: 347
- 79_Tortilla: 325
- 66_SohoCoffee: 305
- 44_Boswell: 363
- 8_Pizzahut: 250
- 31_FlamingGrill: 217
- 9_Subway: 209
- 76_Wasabi: 199
- 6_Dominos: 1,431
- 62_Pho: 102
- 35_KrispyKreme: 187
- 85_RealGreek: 138
- 73_TopGolf: 126
- 45_Brewhouse: 125
- 11_PizzaExpress: 962
- 47_Coffee1: 619
- Not read this month: about 50 chains with scraped web CSV/JSON only (out of scope by the owner's decision), allergen-only PDFs (listed with reasons in `config/skipped_pdfs.yaml`), Zizzi (no PDF), Cookhouse (no PDF), Chicken Cottage (allergen chart only), Five Guys (allergen chart).
- Owner answers of 2026-11-17: the second Mac & Wings PDF (`a9adac8b...`) is another restaurant of Pizza Express (#11) and is read as a fifth source of that chain, region `UK` (the same product names as `1bebca8e...`, so the two Buffalo Wings (6) and (12) No Dip rows that differ are flagged `duplicate ... with different values`; the owner can name the restaurant to split them); the Cornish Bakery allergen book is skipped; the Coffee #1 Ham & Cheese Toastie is read with the new `join_next_page` option of `product_blocks` (Salt 1.40/2.80, weight 215 g; figcheck 0 misses).

## Open-items round (same day, after the first report)

- Boswells drinks (`grouped_table`: new options `own_group_sizes`, `serving_column`, `serving_unit`, `label_gap`, `label_above`): 110 rows, every figure on its page; 12 rows carry error flags that are printed inconsistencies (kJ and kcal do not match, for example 862 kJ against 157 kcal).
- Pho: read by the model (the text layer mixes sub-headings, Vietnamese names and notes): 102 rows (the same count as the text-layer attempt), every figure on its page, a 200 dpi reread differs only in `<1` against `< 1`. The two Spring rolls are named "Spring rolls - Veggie" and "Spring rolls - Pork" after the Vietnamese part of the printed name. Section names are English only ("Curry - Spicy").
- Domino's: pizza pages 3-17 now read as text (`grouped_table`: single rotated letters no longer start a line, `label_centre: range`, `carry_labels`, `label_above` per page); page 18 is the bases table; page 2 (87 pizzas, six tables) from the model with the figures from the text layer (crop bands moved to the new layout, `name_beside_middle_row`). 1,431 rows, no error flags. Printed typos are kept as printed ("Douoble Decadence", "Reduced Fat Mozzarealla Cheese").
- Pizza Express England/Wales/Scotland and Northern Ireland (`numeric_table`: `block_section`, header word `PER`): 476 and 387 rows, 22 error flags in the whole chain that are source inconsistencies. One England row (Pollo Light Mozz Alternative GF) is printed below the page edge: its text is in the text layer but cut off in the page image; it is kept and listed here for the owner.
- Coffee #1: the unchanged April core beverage guide (`drink_tables`) and the Festive beverages, pages 9-12 (72 rows, one per printed size line; `bold_font`, `title_min_size`), the Festive savoury page 7 (four products, model read, every figure on the page). Festive food page 6 keeps three rows whose printed kJ and kcal do not fit (Black Forest Slice, Baked Cranberry & Orange Cheesecake, Stollen Bites), kept as printed.
- Starbucks syrup and cold-foam pages (Autumn 75-76, Holiday 81-82): read by the model, 200 dpi rereads agree, every figure on the page. A sprinkle prints "2 kcal": the cell is read as 2.
- Cornish Bakery (70_Cornish Bakery): an allergen matrix with a kcal figure per product only; skipped by the owner's decision (2026-11-17).
- API spend of this round: [figures kept in the local ledger: `outputs/data-dictionary/_llm_usage.md`].

## Model usage and cost (API, Sonnet 5.5)

The dollar figures of this section (calls, tokens and cost per backend and per PDF, what a clean round costs, the cost of the open-items round) are not kept in this tracked document: the repository is public. They are in the local ledger `work/llm_usage.csv` and in the local copy of this report, `outputs/data-dictionary/end-of-round-report-2026-11.md` (neither is committed; run `uv run python -m pipeline.cli usage` for the tables).

What can be said here: the batch was the first run on the Anthropic API; the API reads 8 pages at once (headless 3) and `vision_table` reads its pages in parallel; the spend cap is $20 per run (`--max-usd` changes it) and a stop writes an interim report; waste in the first round came from Papa John's answers lost to `additionalProperties: false` (quarantined in `work/llm_poisoned-2026-11-16/`), Chef & Brewer instruction changes and a second read of Vue (verification, kept). Budget a round from the local figures and keep the cap.

## Code and tooling changes (tests first)

- `pipeline/llm.py`: API backend uses structured outputs (Sonnet 5.5 rejects forced tool use), plain-JSON fallback for free-form or too complex schemas (Papa John's, Krispy Kreme), `strict_schema`, usage log, spend cap ($20 per run, `--max-usd`), 8 workers on the API, `usage` command, interim report on any stop (runbook 4b).
- `numeric_table`: `name_below` accepts a name with a digit, `wrap_below_lines`; `product_blocks`: `split_blocks`, `footer_y`, `weight_labels`; tools `autotitles.py`, `maxx.py`, `autogolden.py`, `sdk.sh`.

## Remarks for the owner

1. Approvals: every source that produced a CSV (21 chains). Unapproved or removed: see the pending list. Two Mac & Wings PDFs of Pizza Express are both read; they conflict on two rows (Buffalo Wings 6 and 12 No Dip), flagged as duplicates with different values.
2. Goldens were generated by `tools/autogolden.py` (rows with a unique name per source) and are corroborated by `tools/figcheck.py` (every figure on the page text: Starbucks 35,000 figures, Papa John's 7,085, Krispy Kreme 3,332, Ask 6,112, Pizza Hut 1,888, Soho 1,858 and others), by `text_check` (Tesco, Top Golf, Chef & Brewer, Flaming Grill menus) and for Vue by the second read. They were not all checked against rendered pages by eye.
3. Doubtful calls: Chef & Brewer instructions now say how choice lists and add-ons are counted; of its 52 error flags, 14 are kcal ranges printed as such (for example 367-390, kept as printed) and 38 are rows with the same name and different figures (side options and add-ons printed under several dishes), to be reviewed. The Soho drinks matrix prints one figure with a decimal comma (0,3), kept and normalised with a flag. Brewhouse, Vue F'Real and Tortilla keep the PDFs' own kJ/kcal disagreements.
4. The Starbucks Autumn/Holiday books moved their size, figure and allergen columns (config comments give the new x positions).
5. Conflicting Mac & Wings PDFs (Pizza Express, #11), kept as they are by the owner's decision of 2026-11-17: `1bebca8e…` and `a9adac8b…` are two September 2026 Mac & Wings sheets (neither names its restaurant) and disagree on two products. Both rows of each stay in `outputs/11_PizzaExpress.csv`, region `UK`, and carry the flag `error: duplicate of row N with different values`. Buffalo Wings (6) - No Dip: `1bebca8e…` 448 kcal, 4.40 g salt per portion; `a9adac8b…` 403 kcal, 6.00 g salt. Buffalo Wings (12) - No Dip: `1bebca8e…` 895 kcal, 8.80 g salt; `a9adac8b…` 807 kcal, 12.00 g salt. The research team should say which sheet is right (or which restaurant each belongs to).

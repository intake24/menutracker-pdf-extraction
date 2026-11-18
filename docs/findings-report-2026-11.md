# Findings report: November 2026 batch

Written 2026-11-16. Per-source findings; results and cost are in `end-of-round-report-2026-11.md`.

- **Collection shape**: per-chain folders with PDFs and, for about 50 chains, scraper CSV/JSON (nutrition per serving from web sites). The CSV/JSON files are out of scope. 76 PDFs, one duplicated (Farmhouse Inns and Greene King share one allergen PDF).
- **Subway**: five pages (builds on pages 4-5); a `#` footnote marker after the salt figure of Margherita Pizza (`skip_words`).
- **Tortilla**: four new Damn That's Hot pages shifted everything by four; titles in mixed case; hot drinks page read by the API.
- **Wasabi** v34: page groups after page 11 shifted by one; `max_x` recomputed per page with `tools/maxx.py`.
- **Odeon**: a stale text block at x 634-766 on page 1 (`max_x: 620`); a name printed under its figures that contains a digit (`name_below` now accepts it).
- **Soho**: food V16 and a 47-page drinks matrix (Christmas); 305 rows; one printed decimal comma (0,3).
- **Tesco**: only the Christmas GB matrix (no NI). **Cineworld**: two issues, 20 July and 5 November, only the newer is read.
- **Coffee #1**: the October core guide is A4 portrait again (595 pt): `rule_width 450`, `name_size 5.8`, `nutrition_x0 430`; two products without a rule between them (`split_blocks`); one product split over pages 24 and 25 (Ham & Cheese Toastie, left out); the Festive guide prints "Product Weight:" (`weight_labels`) and its page 7 (savoury) has no rules and no PRODUCT header, so the model reads it (checked against the page text); the April core beverages (`drink_tables`) and the Festive beverages (pages 9-12; fonts are CIDFont names, `bold_font: F6`) are read as text.
- **Papa John's**: 79 pages, tables on 7-65 and 69-70; read at 200 dpi on the API. Two API restrictions found: forced tool use is rejected by Sonnet 5.5 (structured outputs now), and `additionalProperties` must be `false` (free-form `values` maps use a plain-JSON request).
- **Vue**: four PDFs (food and ice cream return); the second read differs only in labels (J2O/J20, a note glued to a heading).
- **Krispy Kreme**: Cinnamon book (22 nutrition pages); the schema was "too complex" and timed out as structured output, so it goes as plain JSON.
- **Ask**: the Autumn guide, core tables 40-51 and specials page 35 read as text (382 rows, 0 model calls); pages 36-37 are allergen text.
- **Chef & Brewer**: 11 menu PDFs, 24 pages, kcal in text (`text_check`). Needed three instruction rules (choice lists, one row per printed occurrence, the dish figure first) and a pattern that treats a range `367-390kcal` as one figure and ignores "(under 900kcals)".
- **Flaming Grill**: one A0-size nutrition table (4678 x 3305 pt, read at 110 dpi because the API accepts 8,000 px) and three kcal menus.
- **Real Greek**: the 30 September 2026 menu; the Deliveroo file is dated 18 March 2026.
- **Starbucks**: Autumn and Holiday books, four sources, 3,607 rows; columns moved by 17 to 45 pt.
- **Pizza Express**: England and NI PDFs now print column titles as rotated letters; Mac & Wings and QSR read; a second Mac & Wings PDF (`a9adac8b...`, another restaurant of the chain) is read too and conflicts on two rows (flagged).
- **Boswells** (new, `44_Boswell`): food table read as text (253 rows).

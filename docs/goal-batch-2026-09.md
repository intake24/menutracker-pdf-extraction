# Goal: September 2026 batch (nutrition only)

Status: started 2026-11-06. Same rules and done criteria as `docs/goal-batch-2026-03.md`, with the dates changed. Results go to `outputs/data-dictionary/findings-report-2026-09.md` and `end-of-round-report-2026-09.md`.

## Objective

Parse the 30 PDFs and 5 JPGs in `inputs/` (listed in `inputs/List_of_PDFs_Sept26.xlsx`), extract the nutrition data per food chain into `outputs/<id>_<Key>.csv`, and verify the results with the pipeline's own checks, golden rows and a fresh reviewer. There is no Pearl Scan data.

## Decisions carried over

- No allergen columns (option B). The agent decides `approved: true` and lists every call under "Remarks for the owner". New chains are phase 2.
- Golden files of an earlier PDF with the same name are never overwritten: the source option `golden: <name>__2026-09` names the new file.
- Sources renamed from June keep `approved: true` only while their September run passes the done criteria; a source that does not stays `approved: false` and is listed in the report.
- A source whose document has no September PDF is deleted from its chain (June lesson: one unapproved source stops the chain); a chain with no September PDF at all is left as it is and skipped by `run`.

## Intake (manifest 2026-11-06)

| Chain | September file(s) | Compared with June |
|---|---|---|
| `7_Starbucks` | `SUM2_2026_UK_AllergenBook_CORE_FOOD_v04`, `SUM2_26_UK_AllergenBook_CORE_BEVERAGE_v05` | new issues of the Summer books (the Spring books are gone) |
| `7_Starbucks` | `UK_SUM_AllergenBook_CASTILLO_v03` (22 pages, "Bakery Menu") | new document |
| `8_Pizzahut` | `DINE-IN_AIN_Booklet_C3_2026_FINAL_V1` (13 pages) | new issue, new file name |
| `9_Subway` | `UKI_IngredientsNutritionalInformationJune2026` (3 pages) | new issue |
| `11_PizzaExpress` | `230f6a92…` (England, Wales & Scotland, 24 pages), `43d31e9d…` (Northern Ireland, 20), `79d486ac…` (Mac & Wings, 3), `4248f3d3…` (QSR Brixton, 3) | new issues of PEX, BEL, MW, QSR |
| `24_Zizzi` | `a7bddad7…` (UK V2, 24 pages), `486ec2f5…` (ROI/BEL V1, 28 pages) | new chain (key from Menu Tracker's notebook) |
| `26_PapaJohns` | `nutritional-information` | same name, changed content |
| `35_KrispyKreme` | `UK_Drinks_Allergen_Nutrition_Book_310726` | drinks book; no core book this time |
| `45_Brewhouse` | `6a72028c…_brewhouse_kitchen_core_menu_allergen_matrix_2026_08_04` | new issue |
| `46_Cineworld` | `26-08-13_20Cineworld_…` | new issue |
| `47_Coffee1` | `C1-Core-Food-July-2026-Issue-Date-2307` | new issue; no beverage or birthday book |
| `49_CookhousePub` | `cookhouse_and_pub_main_menu_priceless`, `cookhouse_and_pub_kids_menu_default` | same names, changed content |
| `49_CookhousePub` | `cookhouse_and_pub_breakfast_menu` (2 pages) | new document |
| `52_FiveGuys` | `FGUK_FOH_…_Myprotein_shake_DIGITAL_20260805` | new issue |
| `58_Vue` | `m20685-nutritional-info-sweets`, `m20645-nutritional-info-drinks` | new issues; no food or ice-cream PDF |
| `59_Odeon` | UK nutrition v28 and UK pre-packed matrix v23 | new issues; no Belfast or ROI PDFs |
| `66_SohoCoffee` | `2026-Nutritional-Matrix-Food-V7` | new issue; no drinks matrix |
| `69_TescoCafe` | Summer GB V5, Summer NI V3 | new issues |
| `73_TopGolf` | `legacy_menu` (12 pages) | new document (June had no PDF) |
| `76_Wasabi` | `WAS_Nutritional_Guide-7-160726` | new issue |
| `79_Tortilla` | `tortilla-nutrition-guide-10-aug` | new issue |
| `88_ChickenCottage` | `BOXES.jpg`, `BURGERS.jpg`, `FRIED.jpg`, `GRILLED.jpg`, `SIDES.jpg` (menu boards printing kcal) | new chain; images, not PDFs: `manifest` does not read them yet |

No September file: Domino's, Beefeater, Brewers Fayre, Table Table, Real Greek, Flaming Grill, Ask Italian, Chef & Brewer, Pho.

## Order of work

1. Phase 1: renamed issues of known documents, simplest first (Five Guys, Subway, Tortilla, Cineworld, Odeon, Vue, Papa John's, Coffee #1, Krispy Kreme, Starbucks food and beverage, Pizza Express, Pizza Hut, Wasabi, Soho, Tesco, Brewhouse, Cookhouse main and kids).
2. Phase 2: new documents and chains (Starbucks Castillo, Cookhouse breakfast, Top Golf legacy menu, Zizzi, Chicken Cottage).

## Limits

As in March: report model calls per chain; pause before any single chain goes beyond a rerun of all its pages twice; commit after each chain passes.

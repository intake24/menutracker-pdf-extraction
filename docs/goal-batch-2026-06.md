# Goal: June 2026 batch (nutrition only)

Status: started 2026-11-05. Same rules and done criteria as `docs/goal-batch-2026-03.md`, with the dates changed. Results go to `outputs/data-dictionary/findings-report-2026-06.md` and `end-of-round-report-2026-06.md`.

## Objective

Parse the 47 PDFs in `inputs/` (listed in `inputs/List_of_PDFs_June26.xlsx`), extract the nutrition data per food chain into `outputs/<id>_<Key>.csv`, and verify the results with the pipeline's own checks, golden rows and a fresh reviewer. There is no Pearl Scan data.

## Decisions carried over

- No allergen columns (option B). The agent decides `approved: true` and lists every call under "Remarks for the owner". New chains are phase 2.
- Golden files of an earlier PDF with the same name are never overwritten: the source option `golden: <name>__2026-06` names the new file.
- Sources renamed from March keep `approved: true` only while their June run passes the done criteria; a source that does not stays `approved: false` and is listed in the report.

## What is new compared with March

- New chains (phase 2): Chef & Brewer (4 kcal-only menus, key `20_ChefBrewer`), Pho (`62_Pho`), Wasabi (`76_Wasabi`). Keys follow the Menu Tracker notebook.
- New PDFs for existing chains: Pizza Express QSR Brixton, Vue ice cream, Odeon ROI (nutrition and pre-packed matrix), Starbucks Summer food and beverage, Real Greek Deliveroo menu, Cookhouse kids menu (same name as May 2025 and March), Ask Italian (two new books: Spring/Summer and Concept).
- No June PDF: Topgolf, Flaming Grill, Beefeater, Brewers Fayre, Table Table, Burger King, Odeon Islington matrix, Cookhouse Mother's Day menu (their sources are `approved: false`).

## Limits

As in March: report model calls per chain; pause before any single chain goes beyond a rerun of all its pages twice; commit after each chain passes.

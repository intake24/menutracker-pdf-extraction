# Goal: March 2026 batch (nutrition only)

Status: phase 1 and phase 2 done 2026-10-31 (results: `outputs/data-dictionary/end-of-round-report-2026-03.md`). Written 2026-10-30. Later batches (June 2026, September 2026) reuse this file with the dates changed.

## Objective

Parse the 38 PDFs in `inputs/` (listed in `inputs/PDF_list_Mar26.xlsx`), extract the nutrition data per food chain into `outputs/<id>_<Key>.csv`, and verify the results. There is no Pearl Scan data for this batch, so verification rests on the pipeline's own checks, golden rows and a fresh reviewer.

## Decisions already made

- Allergens are out of scope (option B): the March CSVs carry no allergen columns. The change is made once, in the export step, and covered by a test; golden rows and `eval` compare only the columns both sides have. Whether an unknown allergen marker in a PDF still stops the run is a ruling for the agent to record in the report (default: it does not, because the values are not written).
- Phase 1 is the chains that already exist in `config/chains.yaml`. Phase 2 is the seven new chains: Subway, Ask Italian, Flaming Grill, Soho Coffee, Tesco, Tortilla, The Real Greek.
- The agent proposes and decides `approved: true` for each source. The owner does not approve one by one. Every approval and every doubtful call goes into the final report under "Remarks for the owner".
- Out of scope: Beefeater, Brewers Fayre, Table Table and Burger King (no March PDFs).

## Phase 1: existing chains

1. Apply the renames drafted in `scratchpad/draft_names.py` to `config/chains.yaml` (17 renames), run `manifest`, and confirm no in-scope PDF is `unassigned` except the ones listed below.
2. Decide what to do with the PDFs that have no one-to-one counterpart: Vue drinks (new), Odeon Islington matrix (new), Brewhouse `Food-Allergens-11.25.pdf` (four May menus became one), Cookhouse Mother's Day menu (new; kids menu gone), Coffee #1 Winter Drinks (new), Pizza Express MW (new). Add a source for each or record why not.
3. Run each chain. Where the page count changed (Five Guys, Cineworld, Vue, Odeon, Pizza Hut, Coffee #1, Starbucks, Krispy Kreme) check the page numbers and ranges in the config first.
4. Fix parsers or config until the chain passes the done criteria below. A parser change gets a test first and a fresh reviewer.

## Phase 2: new chains

For each: `scaffold`, look at rendered pages, choose a parser, add the source with `approved: false`, run, read every flag, write golden rows, get a fresh review, then approve. One chain at a time; stop phase 2 for a chain that needs a new parser type and report it instead.

## Done criteria per source

- `manifest` lists the PDF against the chain.
- The run ends without an unhandled error.
- `coverage` shows no unexplained gap: each page is extracted or listed as intentionally skipped.
- `flags` has no unresolved `error`; every `warn` is explained in the report or accepted with a reason.
- Golden rows written from the PDF (same sampling as the May batch: a handful of products per source, including a first, a last and an odd-looking row) and `eval` against golden passes.
- For model-read parsers: `reread` ran and its disagreements are resolved.
- A fresh reviewer has read parsers and config that are new or changed for this batch. The reviewer is the second pair of eyes now that the owner no longer checks each approval.
- The agent sets `approved: true` only when all of the above hold. A source that does not reach this stays `approved: false` and is listed in the report with the reason.

## Rules that stay

Values are copied as printed apart from the flagged clean-ups (`g` and `mg` stripped, decimal comma, thousands comma, `1/2` as `0.5`); problems go to `flags`; an unknown word or label stops the run; similar products stay separate rows; standard headings are applied on write; no real model calls from tests; write the test first; no `Co-Authored-By` trailers; Markdown one line per paragraph; never delete or overwrite `inputs/`, `outputs/`, `work/`, `golden/`; commit to `main` only.

## Limits

- Model calls: the March PDFs are new to the cache, so vision parsers cost real tokens. Report the number of model calls per chain at the end. Pause and ask before any single chain goes beyond a rerun of all its pages twice.
- Time: work phase 1 chain by chain and commit after each chain passes, so a stop leaves a clean state.

## Deliverables

- One CSV per chain in `outputs/`, `_flags.csv` and `_verification.csv` in `outputs/data-dictionary/`.
- Updated `config/chains.yaml`, new `golden/` files, tests for any code change.
- `findings-report-2026-03.md` and `end-of-round-report-2026-03.md` in `outputs/data-dictionary/`, with a "Remarks for the owner" section: every approval the agent gave, every doubtful call, every source left unapproved, and what the playbook should learn for June and September.

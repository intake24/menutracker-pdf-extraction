# Goal: November 2026 batch (nutrition only)

Status: not started (prepared 2026-11-16). Same rules and done criteria as `docs/goal-batch-2026-03.md`, with the dates changed; procedure in `docs/runbook-monthly-batch.md`. Results go to `outputs/data-dictionary/findings-report-2026-11.md` and `end-of-round-report-2026-11.md`, with a copy in `docs/`.

## Objective

Parse the PDFs (and images) the research team puts in `inputs/` (listed in `inputs/List_of_PDFs_Nov26.xlsx`, or whatever that month's list is called), extract the nutrition data per food chain into `outputs/<id>_<Key>.csv`, and verify the results with the pipeline's own checks, the figure-in-page-text check (`tools/figcheck.py`), golden rows and a fresh reviewer. There is no Pearl Scan data.

## Decisions carried over

- No allergen columns (option B). The agent decides `approved: true` and lists every call under "Remarks for the owner". New chains are phase 2.
- Golden files of an earlier PDF with the same name are never overwritten: the source option `golden: <name>__2026-11` names the new file (same-name PDFs every month: Papa John's `nutritional-information`, Cookhouse main and kids menus).
- A source whose document has no PDF this month is deleted from its chain (one unapproved source stops its chain); a chain with no PDF at all stays `approved: false # no November 2026 PDF`.
- Images are converted to one-page PDFs (`<Chain>_<NAME>.pdf`, originals kept) and the conversion is documented in the findings report (the owner agreed in September).
- A source of an earlier issue is recovered from git history (`git show 7bf31f1:config/chains.yaml` is the June config, before the September deletions).

## Starting point

- September 2026: 19 chains with CSVs, 7,994 rows, 30 PDFs plus 5 JPGs; nine chains without a PDF and Five Guys with a PDF that has no nutrition. `docs/end-of-round-report-2026-09.md` has the per-chain state and the doubtful calls.
- Tools: `tools/figcheck.py` (every figure of a model-read PDF on its page), `tools/gcheck.py` (golden file against the PDF text), `tools/cfgedit.py` (rename and drop sources).

## Intake table (fill in after `manifest`)

| Chain | November file(s) | Compared with September |
|---|---|---|
| | | |

## Order of work

1. Phase 1: renamed issues of known documents, simplest first (text-layer chains before model-read chains; see the table in the runbook).
2. Phase 2: new documents and chains (add the key from `~/dev/menutracker/menutracker.ipynb`).
3. End: `run`, `eval`, `coverage`, `flags`, `report`, full tests, fresh reviewer, reports, handoff.

## Limits

As in March: report model calls per chain; pause before any single chain goes beyond a rerun of all its pages twice; commit after each chain passes. The model quota is a 5-hour window: queue the model-read chains (Papa John's 63 pages, Vue 25, Krispy Kreme 20, Soho 20, Tesco 35) one after another in a background script and keep working on text-layer chains meanwhile.

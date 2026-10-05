# Handoff for the next quota window

State on 2026-10-05: thirteen chains live and approved (Krispy Kreme, Pizza Hut and Coffee #1 added 2026-10-05, findings 3.10 to 3.12), `outputs/` holds thirteen CSVs (6,752 rows), 273 tests pass, 66 Pearl Scan mistakes recorded in `config/ground_truth_errata.yaml`. Read `docs/findings-report-2026-10.md` (what was found and the lessons), `docs/chain-mapping-reference.md` (what each chain's PDFs map to) and `docs/playbook-new-batches.md` (how to onboard a chain) first.

## Remaining sources, in the order I would do them

1. Krispy Kreme: done and approved.
2. Pizza Hut: done and approved.
3. Coffee #1: done and approved.
3b. Starbucks: built on branch `starbucks`, `approved: false` in `config/chains.yaml` (findings 3.13); needs the user's approval, then `run`, `eval`, commit.
4. Brewhouse, Cookhouse, Top Golf menus: the dish name is the text before the first comma; judgement and model reads.
5. Final slice: a flags report across all chains, an automatic row-count check for model-read pages, a last review of the whole pipeline.

## Before approving anything

Read every introduction and warning page of the PDF, run `python -m pipeline.cli coverage`, `eval` and (for model-read sources) `pages`, add golden rows for allergens, and keep `config/chains.yaml` approvals with the user.

## Cost guide (points of a 5-hour window)

Config-only chain 1-3, new parser option 3-5, new parser 6-10 plus a review of 3-4, a 65-page model read 15-25.

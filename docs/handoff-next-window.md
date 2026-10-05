# Handoff for the next quota window

State on 2026-10-05: eleven chains live and approved (Krispy Kreme added 2026-10-05, findings 3.10), `outputs/` holds eleven CSVs (5,574 rows), 226 tests pass, 66 Pearl Scan mistakes recorded in `config/ground_truth_errata.yaml`. Read `docs/findings-report-2026-10.md` (what was found and the lessons), `docs/chain-mapping-reference.md` (what each chain's PDFs map to) and `docs/playbook-new-batches.md` (how to onboard a chain) first.

## Remaining sources, in the order I would do them

1. Krispy Kreme: done and approved.
2. Pizza Hut: built on branch `pizza-hut`, `approved: false` in `config/chains.yaml` (findings 3.11); needs the user's approval, then `run`, `eval`, commit.
3. Coffee #1 (food 18 pages with vertical blocks, drinks 28 pages with slanted text; Pearl Scan 92 and 371 rows) and Starbucks (food 20 pages, drinks 73 pages with wrapped names, sizes and milk types; 93 and 1,464 rows). About 8 points each plus a review.
4. Brewhouse, Cookhouse, Top Golf menus: the dish name is the text before the first comma; judgement and model reads.
5. Final slice: a flags report across all chains, an automatic row-count check for model-read pages, a last review of the whole pipeline.

## Before approving anything

Read every introduction and warning page of the PDF, run `python -m pipeline.cli coverage`, `eval` and (for model-read sources) `pages`, add golden rows for allergens, and keep `config/chains.yaml` approvals with the user.

## Cost guide (points of a 5-hour window)

Config-only chain 1-3, new parser option 3-5, new parser 6-10 plus a review of 3-4, a 65-page model read 15-25.

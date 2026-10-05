# Handoff for the next quota window

State on 2026-10-05: Krispy Kreme is built on branch `krispy-kreme` (unapproved, see findings 3.10); ten chains live and approved, `outputs/` holds ten CSVs (5,364 rows), 206 tests pass, 66 Pearl Scan mistakes recorded in `config/ground_truth_errata.yaml`. Read `docs/findings-report-2026-10.md` (what was found and the lessons) and `docs/playbook-new-batches.md` (how to onboard a chain) first.

## Remaining sources, in the order I would do them

1. Krispy Kreme: built, `approved: false` in `config/chains.yaml`; needs the user's approval (see findings 3.10), then `run`, `eval`, commit.
2. Pizza Hut (`Pizza_Hut_Restaurants_Dietary_Information_Booklet_March_2025.pdf`, 24 pages, Pearl Scan has 483 nutrition rows): three layouts (allergen tables with Yes/No and filled or empty circles on pages 2-7, ingredient prose on pages 8-19, per-slice nutrition tables from page 20). Text layer exists. About 10 points.
3. Coffee #1 (food 18 pages with vertical blocks, drinks 28 pages with slanted text; Pearl Scan 92 and 371 rows) and Starbucks (food 20 pages, drinks 73 pages with wrapped names, sizes and milk types; 93 and 1,464 rows). About 8 points each plus a review.
4. Brewhouse, Cookhouse, Top Golf menus: the dish name is the text before the first comma; judgement and model reads.
5. Final slice: a flags report across all chains, an automatic row-count check for model-read pages, a last review of the whole pipeline.

## Before approving anything

Read every introduction and warning page of the PDF, run `python -m pipeline.cli coverage`, `eval` and (for model-read sources) `pages`, add golden rows for allergens, and keep `config/chains.yaml` approvals with the user.

## Cost guide (points of a 5-hour window)

Config-only chain 1-3, new parser option 3-5, new parser 6-10 plus a review of 3-4, a 65-page model read 15-25.

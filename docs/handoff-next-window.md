# Handoff

State on 2026-11-16 (later): the November 2026 round is done (23 chains, 12,942 rows, API spend: see the local ledger, not committed; see `end-of-round-report-2026-11.md`). On 2026-11-17 the owner answered the open questions: the second Mac & Wings PDF is read as another Pizza Express source, the Cornish Bakery book is skipped, and the Coffee #1 Ham & Cheese Toastie is read through the new `join_next_page` option; a fresh review of the first-round parser changes was run (see `goal-batch-2026-11.md`). Earlier the same day: the September 2026 batch was done and committed (19 chains, 7,994 rows, 35 PDFs plus 5 PDFs derived from JPGs; `eval` passes; 333 tests pass, 75 skipped because they read PDFs of earlier batches). Next: the November 2026 collection. Nothing is blocked.

## Start here (in this order)

1. `start-here.md`: what the project is, how a PDF becomes a CSV, the commands, the rules (section 8).
2. `runbook-monthly-batch.md`: the step-by-step for a monthly batch, the per-chain "what changed last time" table, the pitfalls. **This is the page to follow for November.**
3. `goal-batch-2026-11.md`: the goal and decisions for the next batch (intake table to fill in).
4. `end-of-round-report-2026-09.md` and `findings-report-2026-09.md`: the last batch's result, doubtful calls and per-source findings. (Older rounds: `end-of-round-report-2026-10.md`, `findings-report-2026-10.md`; the March and June reports were kept in `outputs/` only.)
5. `playbook-new-batches.md` (layouts, parser options, lessons in sections 5c to 5e) and `chain-mapping-reference.md` (what each chain's CSV means) when you touch a parser or a chain.

## Where things are

- `config/chains.yaml`: 29 chains. 19 approved (September CSVs), 10 `approved: false` (no September PDF, or Five Guys: allergen chart only). Old sources that were deleted in September are in git (`git show 7bf31f1:config/chains.yaml`).
- `inputs/` and `outputs/` still hold the September files: archive them outside the repo before copying the November PDFs in (runbook step 1). Never delete `work/` (model cache), `golden/`, `config/`.
- `tools/`: `figcheck.py`, `gcheck.py`, `cfgedit.py` (see the runbook).
- The September reports are in `docs/` (copies) and `outputs/data-dictionary/` (not in git).

## Open items for the next batch

1. Intake as in the runbook; read the research team's list of PDFs first and ask the owner about any mismatch with `inputs/`.
2. The ten unapproved chains: if a new issue of one arrives, onboard it (recover the old source from git, re-measure pages and columns). Domino's, Real Greek, Ask Italian, Chef & Brewer, Pho and Flaming Grill have a model-read or numeric source from earlier months; Beefeater, Brewers Fayre, Table Table use the Whitbread parsers; Five Guys needs the nutrition guide, not the allergen chart.
3. For every model-read source with an intact text layer run `tools/figcheck.py`; without one (Vue, images) run `reread --pages all` and look at the pages by eye.
4. Write golden files and check each against the page; watch for names shared by two sources (runbook step 5).
4b. Backend choice and the API spend cap are implemented (runbook section 4b, 2026-11-16): `--backend sdk` with a $20 cap per run, usage log, `usage` command, interim report on a stop. The SDK path was verified against the real API on 2026-11-16 (one page identical to the headless read).
5. Known limits that stay: the V/VE check on menus is partial; `eval` compares from the reference side only; `text_check` ignores a few figures on both sides; the SDK backend has only been tested with a fake client (run one page with `--backend sdk` and compare with the cached answer before relying on it); Zizzi has no `menu_section`; Brewhouse, Vue (F'Real), Tortilla, Odeon and Soho print figures that disagree with themselves (kept as printed and flagged); instruction caching for the SDK is not built.
6. Questions still open for the research team (not blocking): the unit of sodium and caffeine differs by source and is not in the column names; whether `manifest` should read images directly (September used derived PDFs).

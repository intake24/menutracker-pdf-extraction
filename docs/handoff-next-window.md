# Handoff

State on 2026-10-06: all 17 food chains are extracted, approved and in `outputs/` (17 CSVs, 8,768 rows, from 35 PDFs); 314 tests pass; `eval` passes with every source checked. Nothing is blocked.

Read in this order: `start-here.md` (how the project works and the rules), `end-of-round-report-2026-10.md` (result, known limits, how to run a batch without Pearl Scan, improvements made before the next batch), `playbook-new-batches.md` (adding chains and layouts), `chain-mapping-reference.md` (what each chain's CSV contains), `findings-report-2026-10.md` (what went wrong in each source).

## Open items for the next batch

0. Intake: run `manifest` (new, changed, unassigned) and `scaffold` for each PDF: `start-here.md` section 7.
1. Run one page with `--backend sdk` and compare the answer with the cached headless one: the SDK path has only been tested with a fake client.
2. For every model-read source of the new batch run `reread --pages all` and check that `report` shows the reread column equal to the model-read pages column.
3. Write golden files with `golden` (allergens, diet cells and nutrition figures) and check every cell against the page or `pdftotext`; ask a second person to spot-check them.
4. Look at the pages `coverage` lists for each new source.
5. Known limits that stay (see section 6 of the end-of-round report): the V/VE check on menus is partial, `eval` compares from the reference side only, `text_check` ignores a few figures on both sides, instruction caching for the SDK is not built.

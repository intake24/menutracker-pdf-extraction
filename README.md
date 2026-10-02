# menutracker-pdf-extraction

Turns the allergen and nutrition PDFs that Menu Tracker scrapes from UK food chains into CSVs, replacing the paid Pearl Scan (human) process. One CSV per chain, one row per food, drink or product.

Design: [docs/pipeline-design.md](docs/pipeline-design.md). Implementation plans: [docs/superpowers/plans/](docs/superpowers/plans/).

## Quick start

Needs Python 3.12, [uv](https://docs.astral.sh/uv/) and poppler (`pdftotext`). `uv sync` installs the Python dependencies, including pdfplumber.

```bash
uv sync
uv run pytest                              # tests read PDFs from inputs/ (not in git)
uv run python -m pipeline.cli manifest     # which parser each PDF in inputs/ uses -> work/manifest.csv
uv run python -m pipeline.cli run          # -> outputs/<id>_<Chain>.csv
uv run python -m pipeline.cli eval         # compare outputs with Pearl Scan and golden rows; exit 1 on failure
```

`run` only builds chains whose sources are all `approved: true` in `config/chains.yaml`; any other chain is skipped with a notice on stderr, or refused with an error if you name it with `--chain`. `eval` skips unapproved chains too.

## Where things live

| Path | In git? | What |
|---|---|---|
| `inputs/` | no | The PDFs. `inputs/ground-truth/<Chain>/` holds Pearl Scan's CSVs. |
| `outputs/` | no | The generated chain CSVs. |
| `config/chains.yaml` | yes | Every chain: its PDFs, which layout parser reads each, region, allergen marker key, approval. |
| `schemas/columns.yaml` | yes | The column dictionary shared by every chain CSV. |
| `pipeline/parsers/` | yes | One parser per PDF **layout** (several chains can share one). |
| `golden/` | yes | See below. |
| `config/ground_truth_errata.yaml` | yes | Known Pearl Scan mistakes, each confirmed against the PDF. |

## Output rules

- Values are written **exactly as the PDF prints them**: no unit or basis conversion, `Trace` / `<0.1` / `Negligible` kept as text.
- Allergen cells are `Yes`, `May contain`, `No` (only when the PDF declares the allergen absent) or blank (the PDF doesn't say). Each source's marker key lives in `config/chains.yaml`; an unknown marker stops the run.
- Problems go into a `flags` column and values are never changed. Flags can come from the PDF itself: some print figures that fail the kJ/kcal or saturates ≤ fat checks.

## How output is checked

`eval` runs two checks.

**Nutrition vs Pearl Scan.** Each PDF's output is compared with its newest Pearl Scan CSV in `inputs/ground-truth/`. At least 99% of its rows must match and every matched cell must agree, except confirmed Pearl Scan errors listed in the errata file. Pearl Scan has no allergen data, so allergens use the second check.

**Allergens vs `golden/`.** Each file in `golden/` is a **hand-picked sample of a few rows**, not a full copy of the PDF. A person checked those rows' allergen cells against the rendered PDF. `eval` requires them to match exactly. They are a spot check that marks land in the right columns, so a golden file with 6 rows for a 148-item PDF is normal. The full output is in `outputs/`.

## Adding a chain

1. Find the chain's key in Menu Tracker's `menutracker.ipynb` (e.g. `16_Beefeater`).
2. Add it to `config/chains.yaml` with each PDF, its layout `parser`, `region`, and (if the PDF has allergen information) the `markers` key, copied from the PDF's own key.
3. Use an existing parser if the layout matches. Otherwise add one in `pipeline/parsers/` and register it in `pipeline/parsers/__init__.py`.
4. Run `eval`. Add `golden/<pdf-stem>.csv` rows for the allergen cells and check them against the PDF by eye.
5. A person sets `approved: true`.

## Onboarding new chains

New batches have no Pearl Scan file to compare with. `docs/playbook-new-batches.md` lists the checks that stand in for it (fail-loud parsing, `python -m pipeline.cli coverage`, arithmetic flags, golden rows), the order of work, the layouts handled and the PDF defects met.

## Status

| Done | Chains |
|---|---|
| Phase 1 | Beefeater, Brewers Fayre, Table Table |
| Phase 2a | Five Guys |
| Phase 2b | Pizza Express (UK and Northern Ireland PDFs) |
| Slice 1 (part) | Cineworld, through the `allergen_matrix` parser (marks matched to allergens by position; `✓` Yes, `▲` May contain, blank = not stated). Pizza Hut is still to do. |

Next: Pizza Hut, then the other text-based layouts (roadmap: `docs/superpowers/plans/2026-10-02-complete-the-pipeline.md`). Vue, Papa John's and Krispy Kreme need a vision route because their text layers are unusable. See §10 of the design doc.

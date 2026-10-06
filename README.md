# menutracker-pdf-extraction

Turns the allergen and nutrition PDFs that Menu Tracker scrapes from UK food chains into CSVs, replacing the paid Pearl Scan (human) process. One CSV per chain, one row per food, drink or product.

**New here? Read [docs/start-here.md](docs/start-here.md)** (how it works, code map, commands, rules, which document answers which question). Agents: see also [AGENTS.md](AGENTS.md). Current state and known limits: [docs/end-of-round-report-2026-10.md](docs/end-of-round-report-2026-10.md). Original design (historical): [docs/pipeline-design.md](docs/pipeline-design.md).

## Quick start

Needs Python 3.12, [uv](https://docs.astral.sh/uv/) and poppler (`pdftotext`). `uv sync` installs the Python dependencies, including pdfplumber.

```bash
uv sync
uv run pytest                              # tests read PDFs from inputs/ (not in git)
uv run python -m pipeline.cli manifest     # which parser each PDF in inputs/ uses -> work/manifest.csv
uv run python -m pipeline.cli run          # -> outputs/<id>_<Chain>.csv
uv run python -m pipeline.cli eval         # compare outputs with Pearl Scan and golden rows; exit 1 on failure (a source with nothing to compare against fails too; --lenient to only warn)
uv run python -m pipeline.cli coverage     # rows against the text layer, per page; lists pages to look at
uv run python -m pipeline.cli flags        # every flagged row -> outputs/_flags.csv
uv run python -m pipeline.cli report       # one line per PDF: rows, flags, golden rows, Pearl Scan, model-read and reread pages -> outputs/_verification.csv
uv run python -m pipeline.cli golden --chain KEY --pdf-stem STEM --rows "Name|Size;Name"   # skeleton of a golden file with every value column
```

Pages the text layer cannot give are read by a model, through headless Claude Code (default, uses the plan login) or the Anthropic SDK (`--backend sdk` or `PIPELINE_LLM_BACKEND=sdk`, needs `ANTHROPIC_API_KEY` and `uv sync --extra sdk`). Both share one cache. `uv run python -m pipeline.cli --backend sdk run` is the same command with the other backend; cost of a round: `docs/sdk-cost-estimate-2026-10.md`.

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

`eval` runs two checks, and `coverage`, `reread` (a second read of model-read pages) and `report` support them.

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

Findings from the first round (errors per source, Pearl Scan mistakes, lessons): `docs/findings-report-2026-10.md`.

## Status

Live and approved (`config/chains.yaml`, output in `outputs/`): Beefeater, Brewers Fayre, Table Table (Whitbread), Five Guys, Pizza Express (UK, NI), Cineworld, Domino's (sides, dips, pizzas), Vue, Odeon (nutrition tables and pre-packed matrices for UK, NI, ROI), Papa John's, Krispy Kreme, Pizza Hut, Coffee #1, Starbucks, Brewhouse, Cookhouse, Top Golf. Seventeen chain CSVs, 8,768 rows. A record of what each chain's PDFs map to is in `docs/chain-mapping-reference.md`. Every compared figure agrees with Pearl Scan except the 75 mistakes recorded in `config/ground_truth_errata.yaml`. The end-of-round report is `docs/end-of-round-report-2026-10.md`.


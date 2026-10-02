import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

from pipeline.columns import load_columns
from pipeline.evaluate import compare_golden, compare_ground_truth, ground_truth_file, read_csv
from pipeline.export import finalise, write_csv
from pipeline.ingest import load_chains, manifest_row, page_texts, text_sha
from pipeline.parsers import PARSERS

ROOT = Path(__file__).resolve().parent.parent


class SourceNotApproved(Exception):
    pass


def manifest(inputs: Path, chains_file: Path, out: Path) -> list[dict]:
    chains = load_chains(chains_file)
    rows = [manifest_row(p, chains) for p in sorted(inputs.glob("*.pdf"))]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return rows


def approved(chain: dict) -> bool:
    return all(source.get("approved") for source in chain["sources"])


def run(inputs: Path, chains_file: Path, outputs: Path, only: str | None = None) -> dict[Path, list[dict]]:
    """Write outputs/<chain key>.csv for every chain whose sources are all approved.

    Chains with an unapproved source are skipped with a notice on stderr; asking for one by name (`only`)
    raises instead. PDFs with identical text, the same parser, markers and columns are parsed once.
    """
    chains = load_chains(chains_file)
    columns = load_columns()
    parsed: dict[tuple, list[dict]] = {}
    written: dict[Path, list[dict]] = {}
    for key, chain in chains.items():
        if only and key != only:
            continue
        if not approved(chain):
            if only:
                raise SourceNotApproved(f"{key}: has a source that is not approved in {chains_file.name}")
            print(f"skipped {key}: not approved in {chains_file.name}", file=sys.stderr)
            continue
        rows: list[dict] = []
        for source in chain["sources"]:
            pdf = inputs / source["pdf"]
            options = {k: v for k, v in source.items() if k not in ("pdf", "region", "category", "approved", "disclaimer")}
            cache_key = (text_sha(page_texts(pdf)), json.dumps(options, sort_keys=True))   # every parse-affecting option
            if cache_key not in parsed:
                parsed[cache_key] = PARSERS[source["parser"]](pdf, source)
            rows += [{"method": "parser"} | r | {"region": source["region"], "source_file": pdf.name}
                     for r in parsed[cache_key]]
        rows = finalise(rows, columns)
        path = outputs / f"{key}.csv"
        write_csv(rows, columns, path)
        written[path] = rows
    return written


def evaluate(chains_file: Path, outputs: Path, ground_truth: Path, golden: Path, config: Path,
             only: str | None = None, strict: bool = False) -> list[str]:
    """Nutrition vs Pearl Scan ground truth, allergens vs hand-verified golden rows. Returns failure lines.

    A source with neither is reported as "not evaluated"; `strict` makes that a failure."""
    mapping = yaml.safe_load((config / "pearlscan_columns.yaml").read_text())
    errata_rows = yaml.safe_load((config / "ground_truth_errata.yaml").read_text()) or []
    failures = []
    for key, chain in load_chains(chains_file).items():
        if not approved(chain) or (only and key != only):
            continue   # `run` skips these, so there is nothing to compare
        out = outputs / f"{key}.csv"
        if not out.exists():
            failures.append(f"{key}: {out.name} missing, run `run` first")
            continue
        ours_all = read_csv(out)
        for source in chain["sources"]:
            stem = Path(source["pdf"]).stem
            ours = [r for r in ours_all if r["source_file"] == source["pdf"]]
            gt = ground_truth_file(ground_truth, stem)
            gold = golden / f"{stem}.csv"
            if gt is None and not gold.exists():
                print(f"{key} {stem}: not evaluated")
                if strict:
                    failures.append(f"{key} {stem}: not evaluated (no ground truth, no golden rows)")
            if gt is not None:
                errata = {(e["item"], e["column"]) for e in errata_rows if e["file"] == gt.name}
                r = compare_ground_truth(read_csv(gt), ours, mapping, errata)
                print(f"{key} {stem}: ground truth {r['rows']} rows, recall {r['recall']:.1%}, "
                      f"{r['cells']} cells, {len(r['mismatches'])} mismatches")
                if not r["passed"]:
                    failures += [f"{key} {stem}: unmatched row {n}" for n in r["unmatched"]]
                    failures += [f"{key} {stem}: {m}" for m in r["mismatches"]]
            if gold.exists():
                msgs = compare_golden(read_csv(gold), ours)
                print(f"{key} {stem}: golden {len(read_csv(gold))} rows, {len(msgs)} failures")
                failures += [f"{key} {stem}: {m}" for m in msgs]
    return failures


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("manifest", help="page/text/parser report for every PDF -> work/manifest.csv")
    run_p = sub.add_parser("run", help="extract every approved chain -> outputs/<key>.csv")
    run_p.add_argument("--chain", help="only this chain key, e.g. 16_Beefeater")
    eval_p = sub.add_parser("eval", help="compare outputs with ground truth and golden rows; exit 1 on any failure")
    eval_p.add_argument("--strict", action="store_true", help="a source with nothing to compare against fails")
    args = parser.parse_args(argv)
    chains_file = ROOT / "config" / "chains.yaml"

    if args.cmd == "manifest":
        rows = manifest(ROOT / "inputs", chains_file, ROOT / "work" / "manifest.csv")
        print(f"{len(rows)} PDFs -> work/manifest.csv; parsers: {dict(Counter(r['parser'] for r in rows))}")
    elif args.cmd == "run":
        for path, rows in run(ROOT / "inputs", chains_file, ROOT / "outputs", args.chain).items():
            errors = sum("error:" in r["flags"] for r in rows)
            warns = sum("warn:" in r["flags"] for r in rows)
            print(f"{path.relative_to(ROOT)}: {len(rows)} rows, {errors} with errors, {warns} with warnings")
    elif args.cmd == "eval":
        failures = evaluate(chains_file, ROOT / "outputs", ROOT / "inputs" / "ground-truth",
                            ROOT / "golden", ROOT / "config", strict=args.strict)
        print("\n".join(failures) or "eval: all checks passed")
        sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

from pipeline.columns import load_columns
from pipeline.coverage import numeric_lines, shortfalls
from pipeline.evaluate import compare_golden, compare_ground_truth, ground_truth_file, read_csv
from pipeline.export import finalise, merge_by_key, write_csv
from pipeline.llm import LlmError
from pipeline.ingest import load_chains, manifest_row, page_texts, text_sha
from pipeline.parsers import PARSERS, vision_pairs, vision_products, vision_table
from pipeline.vision_check import diff_rows, summary

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


def run(inputs: Path, chains_file: Path, outputs: Path, only: str | None = None,
        stopped: list[str] | None = None) -> dict[Path, list[dict]]:
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
        try:
            rows = _parse_chain(chain, inputs, parsed)
        except LlmError as e:   # a rate limit, a cap or a bad answer stops this chain; finished pages stay cached
            message = f"{key}: stopped: {e}"
            print(message, file=sys.stderr)
            if stopped is None:
                raise
            stopped.append(message)
            continue
        if chain.get("merge_by_key"):   # several sources describe the same products (allergen table and nutrition table)
            rows = merge_by_key(rows)
        rows = finalise(rows, columns)
        path = outputs / f"{key}.csv"
        write_csv(rows, columns, path)
        written[path] = rows
    return written


def _parse_chain(chain: dict, inputs: Path, parsed: dict[tuple, list[dict]]) -> list[dict]:
    rows: list[dict] = []
    for source in chain["sources"]:
        pdf = inputs / source["pdf"]
        options = {k: v for k, v in source.items() if k not in ("pdf", "region", "category", "approved", "disclaimer")}
        cache_key = (text_sha(page_texts(pdf)), json.dumps(options, sort_keys=True))   # every parse-affecting option
        if cache_key not in parsed:
            parsed[cache_key] = PARSERS[source["parser"]](pdf, source)
        rows += [{"method": "parser"} | r | {"region": source["region"], "source_file": pdf.name}
                 for r in parsed[cache_key]]
    return rows


def collect_flags(outputs: Path) -> list[dict]:
    """One row per flag of every row of every chain CSV in `outputs`, so source inconsistencies can be reviewed in one place."""
    rows = []
    for path in sorted(outputs.glob("*.csv")):
        if path.name.startswith("_"):
            continue   # reports such as _flags.csv
        for r in read_csv(path):
            for flag in filter(None, (f.strip() for f in r.get("flags", "").split(" | "))):
                level, _, text = flag.partition(": ")
                rows.append({"chain": path.stem, "source_file": r.get("source_file", ""), "source_page": r.get("source_page", ""),
                             "product": r.get("Product_Name", ""), "size": r.get("Size", ""), "level": level, "flag": text})
    return rows


def verification_report(chains_file: Path, outputs: Path, ground_truth: Path, golden: Path) -> list[dict]:
    """One line per source: what was extracted and what it can be checked against, so a person approves from one table.

    No model calls: it reads the chain CSVs, the golden files and the Pearl Scan folder (which may be empty for a new batch)."""
    out = []
    for key, chain in load_chains(chains_file).items():
        path = outputs / f"{key}.csv"
        rows = read_csv(path) if path.exists() else []
        by_pdf: dict[str, list[dict]] = {}
        for source in chain["sources"]:
            by_pdf.setdefault(source["pdf"], []).append(source)   # a PDF can feed several sources (page ranges): one line for the PDF
        for pdf, sources in by_pdf.items():
            source = {**sources[0], "parser": "+".join(dict.fromkeys(s["parser"] for s in sources)), "approved": all(s.get("approved") for s in sources)}
            mine = [r for r in rows if r.get("source_file") == pdf]
            stem = Path(pdf).stem
            gold = golden / f"{stem}.csv"
            llm = [r for r in mine if r.get("method") == "llm"]
            out.append({"chain": key, "source_file": pdf, "parser": source["parser"], "approved": bool(source.get("approved")), "rows": len(mine),
                        "errors": sum("error:" in r.get("flags", "") for r in mine), "warnings": sum("warn:" in r.get("flags", "") for r in mine),
                        "golden_rows": len(read_csv(gold)) if gold.exists() else 0, "pearl_scan": "yes" if ground_truth_file(ground_truth, stem) else "no",
                        "model_read_pages": len({r["source_page"] for r in llm}), "pages_with_rows": len({r["source_page"] for r in mine})})
    return out


def coverage(inputs: Path, chains_file: Path) -> list[str]:
    """For every approved numeric_table source: pages where the text layer has more data-looking lines than rows."""
    out = []
    for key, chain in load_chains(chains_file).items():
        if not approved(chain):
            continue
        for source in chain["sources"]:
            if source["parser"] != "numeric_table":
                continue   # grids and matrices have no number runs to count; vision pages have no usable text
            pdf = inputs / source["pdf"]
            rows = PARSERS["numeric_table"](pdf, source)
            lines = numeric_lines(pdf, max(3, len(source["columns"]) // 2))
            gaps = shortfalls(rows, lines)
            print(f"{key} {pdf.stem}: {len(rows)} rows, {sum(lines.values())} data-looking lines, {len(gaps)} pages short")
            out += [f"{key} {pdf.stem} page {p}: {r} rows for {n} data-looking lines" for p, (r, n) in sorted(gaps.items())]
    return out


VISION = {"vision_table": vision_table, "vision_products": vision_products, "vision_pairs": vision_pairs}


def vision_sources(chains_file: Path, key: str) -> list[tuple[dict, object]]:
    chain = load_chains(chains_file)[key]
    out = [(s, VISION[s["parser"]]) for s in chain["sources"] if s["parser"] in VISION]
    if not out:
        raise SystemExit(f"{key}: no source read by the model")
    return out


def reread(inputs: Path, chains_file: Path, key: str, pages: list[int], dpi: int, only_pdf: str = "") -> list[str]:
    """Read pages again at another resolution (one model call per page) and list every cell that differs from the
    cached first read. A difference means one of the two reads is wrong: look at the page."""
    lines = []
    for source, module in vision_sources(chains_file, key):
        pdf = inputs / source["pdf"]
        for page in pages:
            if only_pdf not in source["pdf"] or page not in module.pages_of(pdf, source):
                continue
            first = module.page_rows(pdf, source, page)
            second = module.page_rows(pdf, {**source, "dpi": dpi}, page, module.WORK / "pages_reread")
            diffs = diff_rows(first, second)
            lines += [f"{key} {pdf.stem} page {page}: {d}" for d in diffs]
            print(f"{key} {pdf.stem} page {page}: {len(first)} rows, {len(diffs)} differences at {dpi} dpi")
    return lines


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
        compared: set[str] = set()   # one PDF can have several sources (page ranges): compare it once, with all their rows
        for source in chain["sources"]:
            if source["pdf"] in compared:
                continue
            compared.add(source["pdf"])
            same_pdf = [s for s in chain["sources"] if s["pdf"] == source["pdf"]]
            source = {**source, "known_gaps": max(s.get("known_gaps", 0) for s in same_pdf)}
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
                truth = read_csv(gt)
                for old, new in source.get("name_fixes", {}).items():   # Pearl Scan corrected a typo the PDF prints
                    for t in truth:
                        t["item_name"] = t["item_name"].replace(old, new)
                r = compare_ground_truth(truth, ours, mapping | source.get("pearlscan", {}), errata,
                                         source.get("known_gaps", 0))
                gap = f", {len(r['unmatched'])} rows in the known gap" if source.get("known_gaps") else ""
                print(f"{key} {stem}: ground truth {r['rows']} rows, recall {r['recall']:.1%}, "
                      f"{r['cells']} cells, {len(r['mismatches'])} mismatches{gap}")
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
    sub.add_parser("coverage", help="pages where the text layer has more data-looking lines than parsed rows (no ground truth needed)")
    pages_p = sub.add_parser("pages", help="per page of a model-read chain: rows, rows with errors, empty cells (from the cache)")
    pages_p.add_argument("--chain", required=True)
    reread_p = sub.add_parser("reread", help="re-read pages of a model-read chain at another dpi and list differing cells (1 call per page)")
    reread_p.add_argument("--chain", required=True)
    reread_p.add_argument("--pages", required=True, help="comma separated page numbers")
    reread_p.add_argument("--dpi", type=int, default=200)
    reread_p.add_argument("--pdf", default="", help="only sources whose file name contains this")
    sub.add_parser("flags", help="every flagged row of every chain -> outputs/_flags.csv (the PDFs' own inconsistencies and parser warnings)")
    sub.add_parser("report", help="one line per source: rows, flags, golden rows, Pearl Scan present, model-read pages -> outputs/_verification.csv (no model calls)")
    eval_p = sub.add_parser("eval", help="compare outputs with ground truth and golden rows; exit 1 on any failure")
    eval_p.add_argument("--strict", action="store_true", help="a source with nothing to compare against fails")
    args = parser.parse_args(argv)
    chains_file = ROOT / "config" / "chains.yaml"

    if args.cmd == "manifest":
        rows = manifest(ROOT / "inputs", chains_file, ROOT / "work" / "manifest.csv")
        print(f"{len(rows)} PDFs -> work/manifest.csv; parsers: {dict(Counter(r['parser'] for r in rows))}")
    elif args.cmd == "run":
        stopped: list[str] = []
        for path, rows in run(ROOT / "inputs", chains_file, ROOT / "outputs", args.chain, stopped).items():
            errors = sum("error:" in r["flags"] for r in rows)
            warns = sum("warn:" in r["flags"] for r in rows)
            print(f"{path.relative_to(ROOT)}: {len(rows)} rows, {errors} with errors, {warns} with warnings")
        if stopped:
            print("\n".join(stopped) + "\nrun again to resume: finished pages are cached", file=sys.stderr)
            sys.exit(1)
    elif args.cmd == "pages":
        vision_sources(chains_file, args.chain)
        written = run(ROOT / "inputs", chains_file, ROOT / "work" / "pages_check", args.chain)
        for rows in written.values():
            for file in sorted({r["source_file"] for r in rows}):
                for page, s in sorted(summary([r for r in rows if r["source_file"] == file]).items()):
                    print(f"{file} page {page}: {s['rows']} rows, {s['flagged']} with errors, {s['empty_cells']} empty cells")
    elif args.cmd == "reread":
        lines = reread(ROOT / "inputs", chains_file, args.chain, [int(p) for p in args.pages.split(",")], args.dpi, args.pdf)
        print("\n".join(lines) or "reread: both reads agree")
        sys.exit(1 if lines else 0)
    elif args.cmd == "report":
        rows = verification_report(chains_file, ROOT / "outputs", ROOT / "inputs" / "ground-truth", ROOT / "golden")
        with (ROOT / "outputs" / "_verification.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        for r in rows:
            print(f"{r['chain']:<16}{r['source_file'][:44]:<46}rows {r['rows']:>5}  err {r['errors']:>3}  warn {r['warnings']:>3}  golden {r['golden_rows']:>3}  pearl {r['pearl_scan']:<3}  model pages {r['model_read_pages']}")
        weak = [r for r in rows if r["golden_rows"] == 0 and r["pearl_scan"] == "no"]
        print(f"{len(rows)} sources; without golden rows or Pearl Scan: {[r['source_file'] for r in weak] or 'none'}")
    elif args.cmd == "flags":
        rows = collect_flags(ROOT / "outputs")
        fields = ["chain", "source_file", "source_page", "product", "size", "level", "flag"]
        with (ROOT / "outputs" / "_flags.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        counts = Counter((r["chain"], r["level"]) for r in rows)
        for (chain, level), n in sorted(counts.items()):
            print(f"{chain}: {n} {level}")
        print(f"{len(rows)} flags -> outputs/_flags.csv")
    elif args.cmd == "coverage":
        gaps = coverage(ROOT / "inputs", chains_file)
        print("\n".join(gaps) or "coverage: every data-looking line has a row")
        sys.exit(1 if gaps else 0)
    elif args.cmd == "eval":
        failures = evaluate(chains_file, ROOT / "outputs", ROOT / "inputs" / "ground-truth",
                            ROOT / "golden", ROOT / "config", strict=args.strict)
        print("\n".join(failures) or "eval: all checks passed")
        sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

from pipeline.columns import PROVENANCE, load_columns
from pipeline.coverage import numeric_lines, page_gaps, shortfalls
from pipeline.evaluate import compare_golden, compare_ground_truth, ground_truth_file, read_csv
from pipeline.export import drop_rows, finalise, merge_by_key, write_csv
from pipeline import llm
from pipeline.llm import LlmError
from pipeline.ingest import load_chains, manifest_row, page_texts, text_sha
from pipeline.parsers import PARSERS, vision_pairs, vision_products, vision_table
from pipeline.vision_check import diff_rows, summary

ROOT = Path(__file__).resolve().parent.parent
DICTIONARY = ROOT / "outputs" / "data-dictionary"


class SourceNotApproved(Exception):
    pass


def manifest(inputs: Path, chains_file: Path, out: Path) -> list[dict]:
    """The page, text and parser report of every PDF in `inputs`, returned with a `status` against the manifest on disk: new (the
    file name was never seen), changed (the name was seen, but with other bytes: a replaced PDF, or image-only pages that were
    re-issued) or same (this name and hash are on record). The file keeps every (name, hash) ever seen, so the same name in a later
    batch gets its own row; rows no longer in `inputs` stay as superseded (the name is there with other bytes) or gone."""
    chains = load_chains(chains_file)
    rows = [manifest_row(p, chains) for p in sorted(inputs.glob("*.pdf"))]
    before = read_csv(out) if out.exists() else []

    def same_version(old: dict, r: dict) -> bool:   # an old manifest without file_sha is judged by its text hash alone
        return old["file"] == r["file"] and (old["file_sha"] == r["file_sha"] if old.get("file_sha") else old["text_sha"] == r["text_sha"])
    for r in rows:
        seen = [o for o in before if o["file"] == r["file"]]
        r["status"] = "new" if not seen else "same" if any(same_version(o, r) for o in seen) else "changed"
    names = {r["file"] for r in rows}
    kept = [o | {"status": "superseded" if o["file"] in names else "gone"} for o in before if not any(same_version(o, r) for r in rows)]
    gone = sorted({o["file"] for o in before if o["status"] != "gone"} - names)
    if gone:
        print(f"removed since the last manifest: {', '.join(gone)}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), restval="")
        w.writeheader()
        w.writerows(rows + kept)
    return rows


def write_report(path: Path, fields: list[str], rows: list[dict]) -> None:
    """The reports about a batch (`flags`, `report`) live in outputs/data-dictionary/ next to the data they describe."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


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
            _retire(outputs / f"{key}.csv")
            continue
        try:
            rows = _parse_chain(chain, inputs, parsed)
        except LlmError as e:   # a rate limit, a cap or a bad answer stops this chain; finished pages stay cached
            message = f"{key}: stopped: {e}"
            print(message, file=sys.stderr)
            if stopped is None:
                raise
            stopped.append(message)
            _retire(outputs / f"{key}.csv")
            continue
        if chain.get("merge_by_key"):   # several sources describe the same products (allergen table and nutrition table)
            rows = merge_by_key(rows)
        rows = finalise(rows, columns)
        path = outputs / f"{key}.csv"
        write_csv(rows, columns, path)
        written[path] = rows
    return written


def apply_backend(name: str | None) -> None:
    """`--backend` wins over the PIPELINE_LLM_BACKEND environment variable (already read into llm.BACKEND)."""
    if name is None:
        name = llm.BACKEND
    if name not in llm.BACKENDS:
        raise SystemExit(f"unknown backend {name!r}: use one of {llm.BACKENDS}")
    llm.BACKEND = name


def _retire(path: Path) -> None:
    """A chain that was skipped or stopped must not leave its CSV of an earlier run looking current: it moves to outputs/_stale/."""
    if path.exists():
        (path.parent / "_stale").mkdir(exist_ok=True)
        path.replace(path.parent / "_stale" / path.name)
        print(f"moved the old {path.name} to {path.parent.name}/_stale/", file=sys.stderr)


def _parse_chain(chain: dict, inputs: Path, parsed: dict[tuple, list[dict]]) -> list[dict]:
    rows: list[dict] = []
    for source in chain["sources"]:
        pdf = inputs / source["pdf"]
        options = {k: v for k, v in source.items() if k not in ("pdf", "region", "category", "approved", "disclaimer", "drop_rows")}
        # every parse-affecting option, and the bytes of the file: image-only PDFs have no text, so equal text would not mean equal pages
        cache_key = (text_sha(page_texts(pdf)), hashlib.sha256(pdf.read_bytes()).hexdigest(), json.dumps(options, sort_keys=True))
        if cache_key not in parsed:
            parsed[cache_key] = PARSERS[source["parser"]](pdf, source)
        rows += [{"method": "parser"} | r | {"region": source["region"], "source_file": pdf.name}
                 for r in drop_rows(parsed[cache_key], source.get("drop_rows", []))]
    return rows


def collect_flags(outputs: Path) -> list[dict]:
    """One row per flag of every row of every chain CSV in `outputs`, so source inconsistencies can be reviewed in one place."""
    rows = []
    for path in sorted(outputs.glob("*.csv")):
        if path.name.startswith("_"):
            continue   # leftover files starting with _
        for r in read_csv(path):
            for flag in filter(None, (f.strip() for f in r.get("flags", "").split(" | "))):
                level, _, text = flag.partition(": ")
                rows.append({"chain": path.stem, "source_file": r.get("source_file", ""), "source_page": r.get("source_page", ""),
                             "product": r.get("Product_Name", ""), "size": r.get("Size", ""), "level": level, "flag": text})
    return rows


def verification_report(chains_file: Path, outputs: Path, ground_truth: Path, golden: Path, reread_log: Path | None = None) -> list[dict]:
    """One line per source: what was extracted and what it can be checked against, so a person approves from one table.

    No model calls: it reads the chain CSVs, the golden files and the Pearl Scan folder (which may be empty for a new batch)."""
    out = []
    logged = read_csv(reread_log) if reread_log is not None and reread_log.exists() else []
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
                        "model_read_pages": len({r["source_page"] for r in llm}), "pages_with_rows": len({r["source_page"] for r in mine}),
                        "reread_pages": len({r["page"] for r in logged if r["chain"] == key and r["source_file"] == pdf}),
                        "reread_differences": sum(int(r["differences"]) for r in logged if r["chain"] == key and r["source_file"] == pdf),
                        "exact_duplicates": len(mine) - len({tuple(sorted((k, v) for k, v in r.items() if k not in PROVENANCE)) for r in mine})})
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


def write_golden_skeleton(outputs: Path, golden: Path, key: str, stem: str, picks: list[str]) -> Path:
    """golden/<stem>.csv with every value column of the chain CSV (allergens, diet, nutrients, notes; not the provenance, the
    ingredient text or the flags) for the chosen rows ("Name" or "Name|Size"). The cells are copied from the pipeline's output:
    a person must check each one against the page (figures against `pdftotext` or the image) before the file counts as golden."""
    path = golden / f"{stem}.csv"
    if path.exists():
        raise FileExistsError(f"{path} exists: edit it by hand, or delete it first")
    rows = read_csv(outputs / f"{key}.csv")
    skip = set(PROVENANCE) | {"Ingredients", "Product_Description"}
    columns = [c for c in rows[0] if c not in skip]
    chosen = []
    for pick in picks:
        name, _, size = pick.partition("|")
        found = [r for r in rows if r["Product_Name"] == name.strip() and (not size or r.get("Size", "") == size.strip())]
        if not found:
            raise SystemExit(f"no row {pick!r} in {key}")
        chosen.append(found[0])
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in columns} for r in chosen)
    return path


def review_pages(inputs: Path, chains_file: Path, outputs: Path) -> list[str]:
    """For every approved source with figures in its text layer, any layout: pages with fewer rows than the text layer suggests.

    Meant as a list for a person to open, not a pass or fail: an intro page or a wrapped line can add a data-looking line."""
    out = []
    for key, chain in load_chains(chains_file).items():
        path = outputs / f"{key}.csv"
        if not approved(chain) or not path.exists():
            continue
        rows = read_csv(path)
        for pdf in dict.fromkeys(s["pdf"] for s in chain["sources"]):
            lines = numeric_lines(inputs / pdf, 3)
            if sum(lines.values()) < 5:
                continue   # no figures in the text layer (images, or kcal in words): row counts come from the model checks instead
            mine = [r for r in rows if r.get("source_file") == pdf]
            for page, (have, expected) in sorted(page_gaps(mine, lines).items()):
                out.append(f"{key} {pdf} page {page}: {have} rows, about {expected} expected from the text layer")
    return out


VISION = {"vision_table": vision_table, "vision_products": vision_products, "vision_pairs": vision_pairs}


def vision_sources(chains_file: Path, key: str) -> list[tuple[dict, object]]:
    chain = load_chains(chains_file)[key]
    out = [(s, VISION[s["parser"]]) for s in chain["sources"] if s["parser"] in VISION]
    if not out:
        raise SystemExit(f"{key}: no source read by the model")
    return out


def reread(inputs: Path, chains_file: Path, key: str, pages: list[int] | None, dpi: int, only_pdf: str = "", log: Path | None = None) -> list[str]:
    """Read pages again at another resolution (one model call per page) and list every cell that differs from the
    cached first read. A difference means one of the two reads is wrong: look at the page.

    `pages` None means every page the model reads for the chain. Each page read is appended to `log` (chain, pdf, page, dpi, rows,
    differences) so that `report` can show what was reread."""
    lines = []
    for source, module in vision_sources(chains_file, key):
        pdf = inputs / source["pdf"]
        for page in (module.pages_of(pdf, source) if pages is None else pages):
            if only_pdf not in source["pdf"] or page not in module.pages_of(pdf, source):
                continue
            first = module.page_rows(pdf, source, page)
            second = module.page_rows(pdf, {**source, "dpi": dpi}, page, module.WORK / "pages_reread")
            diffs = diff_rows(first, second)
            lines += [f"{key} {pdf.stem} page {page}: {d}" for d in diffs]
            print(f"{key} {pdf.stem} page {page}: {len(first)} rows, {len(diffs)} differences at {dpi} dpi")
            if log is not None:
                new = not log.exists()
                log.parent.mkdir(parents=True, exist_ok=True)
                with log.open("a", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=["chain", "source_file", "page", "dpi", "rows", "differences"])
                    if new:
                        w.writeheader()
                    w.writerow({"chain": key, "source_file": source["pdf"], "page": page, "dpi": dpi, "rows": len(first), "differences": len(diffs)})
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
    parser.add_argument("--backend", choices=llm.BACKENDS, default=None,
                        help="how pages are read by the model: claude-code (headless `claude -p`, the plan login; default) or sdk (Anthropic API, ANTHROPIC_API_KEY); "
                             "or set PIPELINE_LLM_BACKEND")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("manifest", help="page/text/parser report for every PDF -> work/manifest.csv")
    run_p = sub.add_parser("run", help="extract every approved chain -> outputs/<key>.csv")
    run_p.add_argument("--chain", help="only this chain key, e.g. 16_Beefeater")
    sub.add_parser("coverage", help="pages where the text layer has more data-looking lines than parsed rows (no ground truth needed)")
    pages_p = sub.add_parser("pages", help="per page of a model-read chain: rows, rows with errors, empty cells (from the cache)")
    pages_p.add_argument("--chain", required=True)
    reread_p = sub.add_parser("reread", help="re-read pages of a model-read chain at another dpi and list differing cells (1 call per page)")
    reread_p.add_argument("--chain", required=True)
    reread_p.add_argument("--pages", required=True, help='comma separated page numbers, or "all" for every page the model reads')
    reread_p.add_argument("--dpi", type=int, default=200)
    reread_p.add_argument("--pdf", default="", help="only sources whose file name contains this")
    sub.add_parser("flags", help="every flagged row of every chain -> outputs/data-dictionary/_flags.csv (the PDFs' own inconsistencies and parser warnings)")
    sub.add_parser("report", help="one line per source: rows, flags, golden rows, Pearl Scan present, model-read pages -> outputs/data-dictionary/_verification.csv (no model calls)")
    scaffold_p = sub.add_parser("scaffold", help="draft the chains.yaml entry for a new or updated PDF (prints it; edits nothing)")
    scaffold_p.add_argument("--chain", required=True, help="the chain key, e.g. 16_Beefeater (a new chain: <id>_<Name> from menutracker.ipynb)")
    scaffold_p.add_argument("--pdf", required=True, help="file name in inputs/")
    scaffold_p.add_argument("--out", help="also write the draft to this file")
    golden_p = sub.add_parser("golden", help="write golden/<pdf stem>.csv with every value column for the chosen rows, to be checked against the page by hand")
    golden_p.add_argument("--chain", required=True)
    golden_p.add_argument("--pdf-stem", required=True)
    golden_p.add_argument("--rows", required=True, help='rows separated by ";", each "Name" or "Name|Size"')
    eval_p = sub.add_parser("eval", help="compare outputs with ground truth and golden rows; exit 1 on any failure")
    eval_p.add_argument("--lenient", action="store_true", help="a source with nothing to compare against only prints a notice (default: it fails, so a new batch cannot pass unchecked)")
    args = parser.parse_args(argv)
    apply_backend(args.backend)
    chains_file = ROOT / "config" / "chains.yaml"

    if args.cmd == "manifest":
        rows = manifest(ROOT / "inputs", chains_file, ROOT / "work" / "manifest.csv")
        print(f"{len(rows)} PDFs -> work/manifest.csv; parsers: {dict(Counter(r['parser'] for r in rows))}")
        counts = Counter(r["status"] for r in rows)
        print(f"since the last manifest: {counts['new']} new, {counts['changed']} changed, {counts['same']} same; {sum(r['parser'] == 'unassigned' for r in rows)} unassigned")
        for r in rows:
            if r["status"] != "same" or r["parser"] == "unassigned":
                print(f"  {r['status']:<8}{r['file']}  ({r['parser']})")
        if counts["new"] + counts["changed"] or any(r["parser"] == "unassigned" for r in rows):
            print("next: python -m pipeline.cli scaffold --chain KEY --pdf FILE  (drafts the config entry; see docs/start-here.md)")
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
        lines = reread(ROOT / "inputs", chains_file, args.chain, None if args.pages == "all" else [int(p) for p in args.pages.split(",")], args.dpi, args.pdf,
                       ROOT / "work" / "reread_log.csv")
        print("\n".join(lines) or "reread: both reads agree")
        sys.exit(1 if lines else 0)
    elif args.cmd == "report":
        rows = verification_report(chains_file, ROOT / "outputs", ROOT / "inputs" / "ground-truth", ROOT / "golden", ROOT / "work" / "reread_log.csv")
        write_report(DICTIONARY / "_verification.csv", list(rows[0]), rows)
        for r in rows:
            print(f"{r['chain']:<16}{r['source_file'][:44]:<46}rows {r['rows']:>5}  err {r['errors']:>3}  warn {r['warnings']:>3}  dup {r['exact_duplicates']:>3}  golden {r['golden_rows']:>3}  pearl {r['pearl_scan']:<3}  model pages {r['model_read_pages']:>3}  reread {r['reread_pages']:>3} ({r['reread_differences']} diff)")
        weak = [r for r in rows if r["golden_rows"] == 0 and r["pearl_scan"] == "no"]
        print(f"{len(rows)} sources; without golden rows or Pearl Scan: {[r['source_file'] for r in weak] or 'none'}")
    elif args.cmd == "scaffold":
        from pipeline.scaffold import draft_entry, layout_features
        pdf = ROOT / "inputs" / args.pdf
        if not pdf.exists():
            raise SystemExit(f"{pdf} does not exist: put the PDF in inputs/ first")
        draft = draft_entry(load_chains(chains_file), args.chain, args.pdf, layout_features(pdf))
        print(draft)
        if args.out:
            Path(args.out).write_text(draft)
            print(f"(also written to {args.out}; nothing was added to config/chains.yaml)")
    elif args.cmd == "golden":
        path = write_golden_skeleton(ROOT / "outputs", ROOT / "golden", args.chain, args.pdf_stem, [p for p in args.rows.split(";") if p.strip()])
        print(f"{path.relative_to(ROOT)} written: check every cell against the page, then commit it")
    elif args.cmd == "flags":
        rows = collect_flags(ROOT / "outputs")
        fields = ["chain", "source_file", "source_page", "product", "size", "level", "flag"]
        write_report(DICTIONARY / "_flags.csv", fields, rows)
        counts = Counter((r["chain"], r["level"]) for r in rows)
        for (chain, level), n in sorted(counts.items()):
            print(f"{chain}: {n} {level}")
        print(f"{len(rows)} flags -> outputs/data-dictionary/_flags.csv")
    elif args.cmd == "coverage":
        gaps = coverage(ROOT / "inputs", chains_file)
        review = review_pages(ROOT / "inputs", chains_file, ROOT / "outputs")
        if review:
            print("pages to look at (any layout; a list, not a failure):\n" + "\n".join(review))
        print("\n".join(gaps) or "coverage: every data-looking line has a row")
        sys.exit(1 if gaps else 0)
    elif args.cmd == "eval":
        failures = evaluate(chains_file, ROOT / "outputs", ROOT / "inputs" / "ground-truth",
                            ROOT / "golden", ROOT / "config", strict=not args.lenient)
        print("\n".join(failures) or "eval: all checks passed")
        sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

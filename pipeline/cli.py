import argparse
import csv
from collections import Counter
from pathlib import Path

from pipeline.ingest import load_chains, manifest_row

ROOT = Path(__file__).resolve().parent.parent


def manifest(inputs: Path, chains_file: Path, out: Path) -> list[dict]:
    chains = load_chains(chains_file)
    rows = [manifest_row(p, chains) for p in sorted(inputs.glob("*.pdf"))]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return rows


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("manifest", help="page/text/parser report for every PDF -> work/manifest.csv")
    args = parser.parse_args(argv)

    if args.cmd == "manifest":
        rows = manifest(ROOT / "inputs", ROOT / "config" / "chains.yaml", ROOT / "work" / "manifest.csv")
        print(f"{len(rows)} PDFs -> work/manifest.csv; parsers: {dict(Counter(r['parser'] for r in rows))}")


if __name__ == "__main__":
    main()

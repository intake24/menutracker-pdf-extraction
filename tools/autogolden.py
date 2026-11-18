"""Write golden files for the sources of a batch that have none: per source up to N rows (first, last and evenly spread) whose name appears once in the whole chain CSV
(so the `golden` command cannot pick another source's row of the same name). The rows are the pipeline's own output: this only prepares the files; they still have to be
checked against the PDF (tools/gcheck.py, tools/figcheck.py, the rendered page) before the source is approved.

Usage: python tools/autogolden.py [CHAIN_KEY ...] [--n 5]   (default: every approved chain; sources with a golden file already are skipped)
"""
import collections
import csv
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    args = sys.argv[1:]
    n = 5
    if "--n" in args:
        k = args.index("--n")
        n = int(args[k + 1])
        del args[k:k + 2]
    chains = yaml.safe_load((ROOT / "config" / "chains.yaml").read_text())
    for key, chain in chains.items():
        if args and key not in args:
            continue
        out = ROOT / "outputs" / f"{key}.csv"
        if not out.exists():
            continue
        rows = list(csv.DictReader(out.open()))
        names = collections.Counter((r["item_name"], r.get("Size", "")) for r in rows)
        for source in chain["sources"]:
            stem = source.get("golden") or Path(source["pdf"]).stem
            if (ROOT / "golden" / f"{stem}.csv").exists():
                continue
            mine = [r for r in rows if r["source_file"] == source["pdf"] and names[(r["item_name"], r.get("Size", ""))] == 1
                    and ";" not in r["item_name"] and "|" not in r["item_name"] and r["item_name"] not in {x["item_name"] for x in rows if x["source_file"] != source["pdf"]}]
            if not mine:
                print(f"{key} {stem}: no row with a unique name")
                continue
            idx = sorted({round(i * (len(mine) - 1) / (min(n, len(mine)) - 1)) for i in range(min(n, len(mine)))}) if len(mine) > 1 and n > 1 else [0]
            spec = ";".join(f"{mine[i]['item_name']}|{mine[i].get('Size', '')}" if mine[i].get("Size") else mine[i]["item_name"] for i in idx)
            r = subprocess.run([sys.executable, "-m", "pipeline.cli", "golden", "--chain", key, "--pdf-stem", stem, "--rows", spec], cwd=ROOT, capture_output=True, text=True)
            print(f"{key} {stem}: {(r.stdout + r.stderr).strip().splitlines()[-1][:110]}")


if __name__ == "__main__":
    main()

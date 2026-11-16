"""Second check of a golden file against the PDF text layer (a cheap look before the by-eye check against the rendered page).

Usage: GW=<lines> python tools/gcheck.py golden/<stem>.csv inputs/<stem>.pdf

For each golden row it looks for a text line that holds the first words of the product name and checks that every numeric cell of the row is a token within GW lines around it (default 3). Layouts differ: one-line rows (Pizza Express, Subway, Tortilla) work with GW=2; blocks of figures printed in a column beside a name (Coffee #1, Krispy Kreme, Starbucks beverages) need GW=12 to 30. Thousands commas in the PDF are ignored. A MISSING row is not necessarily wrong (a name that wraps over lines, two sources sharing a name): look at the page. Never a substitute for looking at the page.
"""
import csv
import os
import re
import subprocess
import sys


def main(golden: str, pdf: str) -> int:
    text = subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True).stdout.split("\n")
    window = int(os.environ.get("GW", "3"))
    bad = 0
    for row in csv.DictReader(open(golden)):
        name = row["Product_Name"]
        first = name.split(" (")[0].split()
        candidates = [i for i, line in enumerate(text) if all(w in line for w in first[:2]) or name[:12] in line]
        values = [v for k, v in row.items() if k not in ("Product_Name", "Category") and v and re.fullmatch(r"[<\d.]+", v)]
        ok = False
        for i in candidates:
            near = re.sub(r"(?<=\d),(?=\d{3})", "", " ".join(text[max(0, i - window): i + window + 1]))
            tokens = near.split()
            if all(v in tokens or v.replace("<", "") in near for v in values):
                ok = True
                break
        print("OK     " if ok else "MISSING", name, "" if ok else values)
        bad += not ok
    print("bad", bad)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))

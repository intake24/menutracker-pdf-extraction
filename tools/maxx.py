"""Suggest a per-page `max_x` for a numeric_table whose figures are followed by Y/N columns (Wasabi): the midpoint between the last figure left of the first Y or N cell and that cell.

Usage: python tools/maxx.py inputs/<file>.pdf 4-13,15
Prints `{page: x, ...}` ready to paste into `max_x:` (a page with no Y/N cell is left out: it needs no cut). Check the result on a rendered page; the first Y/N cell must be right of every figure of the table.
"""
import re
import sys

import pdfplumber

NUMBER = re.compile(r"^\d+(\.\d+)?$")


def pages(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += range(int(a), int(b or a) + 1)
    return out


def main(pdf: str, spec: str) -> None:
    doc = pdfplumber.open(pdf)
    result = {}
    for n in pages(spec):
        words = doc.pages[n - 1].extract_words()
        first = min((w["x0"] for w in words if w["text"] in ("Y", "N") and w["x0"] < 800), default=None)
        if first is None:
            continue
        last = max((w["x1"] for w in words if NUMBER.match(w["text"]) and w["x1"] < first and w["top"] > 120), default=None)
        if last is not None:
            result[n] = round((first + last) / 2, 1)
    print("{" + ", ".join(f"{k}: {v}" for k, v in result.items()) + "}")


if __name__ == "__main__":
    main(*sys.argv[1:3])

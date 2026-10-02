"""Checks for pages read by the model, where no text layer or ground truth can confirm the rows.

`summary` lists, per page, how many rows were read, how many carry problem flags and how many cells are empty, so a
person can look at the odd pages first. `diff_rows` compares two reads of the same page (a re-read at another
resolution, see `cli reread`): any cell that differs is a place one of the reads is wrong.
"""
from collections import Counter, defaultdict

from pipeline.columns import PROVENANCE

SKIP = set(PROVENANCE) | {"source_page"}


def _plain(value: str) -> str:
    return value.replace("–", "-").replace("—", "-") if isinstance(value, str) else value   # the model varies dashes


def summary(rows: list[dict]) -> dict[int, dict]:
    """page -> rows read, rows with error flags, and cells empty in a row although another row of the page has them."""
    by_page: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_page[r["source_page"]].append(r)
    out = {}
    for page, rs in by_page.items():
        used = {k for r in rs for k, v in r.items() if k not in SKIP and v not in (None, "")}
        out[page] = {"rows": len(rs), "flagged": sum("error:" in r.get("flags", "") for r in rs),
                     "empty_cells": sum(r.get(c) in (None, "") for r in rs for c in used)}
    return out


def diff_rows(old: list[dict], new: list[dict]) -> list[str]:
    """Rows paired by (Product_Name, Size) in order of occurrence; cells and missing or extra rows reported."""
    def keyed(rows):
        seen, out = Counter(), {}
        for r in rows:
            k = (r["Product_Name"], r.get("Size", "").replace("–", "-").replace("—", "-"))   # the model varies dashes
            out[(*k, seen[k])] = r
            seen[k] += 1
        return out
    a, b = keyed(old), keyed(new)
    lines = []
    for key in sorted(set(a) | set(b), key=lambda k: (k[0], k[1], k[2])):
        label = f"{key[0]} {key[1]}".strip()
        if key not in b:
            lines.append(f"row only in the first read: {label}")
        elif key not in a:
            lines.append(f"row only in the re-read: {label}")
        else:
            for col in sorted((set(a[key]) | set(b[key])) - SKIP):
                if _plain(a[key].get(col, "")) != _plain(b[key].get(col, "")):
                    lines.append(f"{label}.{col}: {a[key].get(col, '')!r} vs {b[key].get(col, '')!r}")
    return lines

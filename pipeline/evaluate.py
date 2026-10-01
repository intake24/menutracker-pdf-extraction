"""Compare our output with Pearl Scan ground truth (nutrition) and hand-verified golden rows (allergens)."""
import csv
import re
from pathlib import Path

ROW_RECALL_MIN = 0.99


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def same(want: str, got: str) -> bool:
    try:
        return float(want) == float(got)
    except ValueError:
        return want.strip().casefold() == got.strip().casefold()


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def ground_truth_file(gt_dir: Path, pdf_stem: str) -> Path | None:
    """Newest Pearl Scan CSV for a PDF: `<stem>_v0.1.csv` beats `<stem>.csv`; `Previous/` is ignored."""
    found = [p for p in gt_dir.rglob("*.csv")
             if "Previous" not in p.parts and p.stem in (pdf_stem, f"{pdf_stem}_v0.1")]
    return max(found, key=lambda p: p.stem.endswith("_v0.1"), default=None)


def compare_ground_truth(truth: list[dict], ours: list[dict], mapping: dict[str, str],
                         errata: set[tuple[str, str]]) -> dict:
    """Match rows on name (+ size), then compare every mapped cell.

    errata: {(item_name, pearlscan_column)}; column "*" excuses a whole row.
    """
    by_key: dict[str, dict] = {}
    for r in ours:
        by_key.setdefault(norm(r["Product_Name"] + r.get("Size", "")), r)
    unmatched, mismatches, cells = [], [], 0
    for t in truth:
        name = t["item_name"]
        if (name, "*") in errata:
            continue
        o = by_key.get(norm(name))
        if o is None:
            unmatched.append(name)
            continue
        for gt_col, col in mapping.items():
            if gt_col not in t or gt_col == "item_name" or (name, gt_col) in errata:
                continue
            cells += 1
            if not same(t[gt_col], o.get(col, "")):
                mismatches.append(f"{name}.{gt_col}: Pearl Scan {t[gt_col]!r}, ours {o.get(col, '')!r}")
    checked = len(truth) - sum((t["item_name"], "*") in errata for t in truth)
    recall = (checked - len(unmatched)) / checked if checked else 1.0
    return {"rows": checked, "recall": recall, "cells": cells, "unmatched": unmatched, "mismatches": mismatches,
            "passed": recall >= ROW_RECALL_MIN and not mismatches}


def compare_golden(golden: list[dict], ours: list[dict]) -> list[str]:
    """Every golden row (matched on Product_Name + Category) must exist with identical cells."""
    by_key = {(r["Product_Name"], r["Category"]): r for r in ours}
    failures = []
    for g in golden:
        o = by_key.get((g["Product_Name"], g["Category"]))
        if o is None:
            failures.append(f"missing row: {g['Product_Name']} ({g['Category']})")
            continue
        for col, want in g.items():
            got = o.get(col)
            if got is None:
                failures.append(f"{g['Product_Name']}: column {col!r} not in output")
            elif not same(want, got):
                failures.append(f"{g['Product_Name']}.{col}: expected {want!r}, got {got!r}")
    return failures

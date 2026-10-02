"""Compare our output with Pearl Scan ground truth (nutrition) and hand-verified golden rows (allergens)."""
import csv
import io
import re
import unicodedata
from pathlib import Path

ROW_RECALL_MIN = 0.99


def _decode(line: bytes) -> str:
    try:
        return line.decode("utf-8")
    except UnicodeDecodeError:
        return line.decode("cp1252")


def read_csv(path: Path) -> list[dict]:
    """Read a CSV as UTF-8, or as Windows-1252 where a line isn't (Pearl Scan files edited in Excel; some mix both)."""
    raw = path.read_bytes().removeprefix(b"\xef\xbb\xbf")
    text = "".join(_decode(line) for line in raw.splitlines(keepends=True))
    return list(csv.DictReader(io.StringIO(text, newline="")))


def same(want: str, got: str) -> bool:
    try:
        return float(want) == float(got)
    except ValueError:
        return want.strip().casefold() == got.strip().casefold()


def norm(text: str) -> str:
    """Name key: letters and digits only, accents dropped (Pearl Scan lost some: BACARDI for BACARDÍ)."""
    plain = unicodedata.normalize("NFKD", re.sub("[™®©]", "", text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", plain.casefold())


def _stem_key(stem: str) -> str:
    """File-name stem without soft hyphens, zero-width characters or `%20`/`_20` for spaces (Pearl Scan names vary)."""
    stem = unicodedata.normalize("NFKC", stem)
    stem = re.sub("[\u00ad\u200b\u200c\u200d\ufeff]", "", stem)
    return re.sub(r"%20|_20", " ", stem)


def ground_truth_file(gt_dir: Path, pdf_stem: str) -> Path | None:
    """Newest Pearl Scan CSV for a PDF: `<stem>_v0.1.csv` beats `<stem>.csv`; `Previous/` is ignored."""
    want = _stem_key(pdf_stem)
    found = [p for p in gt_dir.rglob("*.csv")
             if "Previous" not in p.parts and _stem_key(p.stem) in (want, f"{want}_v0.1")]
    return max(found, key=lambda p: p.stem.endswith("_v0.1"), default=None)


def _full_name(row: dict) -> str:
    """Pearl Scan's item name: product, then cheese and crust where the PDF has them, then size."""
    return " ".join(row.get(k, "") for k in ("Product_Name", "Cheese", "Crust", "Size"))


def _clean(name: str) -> str:
    """A name without bracketed notes and anything after a star: Pearl Scan dropped those from item names."""
    return re.sub(r"\*.*$|\([^)]*\)", " ", name)


def compare_ground_truth(truth: list[dict], ours: list[dict], mapping: dict[str, str],
                         errata: set[tuple[str, str]]) -> dict:
    """Match rows on name (+ size), then compare every mapped cell.

    errata: {(item_name, pearlscan_column)}; column "*" excuses a whole row.
    """
    by_key: dict[str, list[dict]] = {}
    for r in ours:
        by_key.setdefault(norm(_full_name(r)), []).append(r)
    alt: dict[str, list[dict]] = {}
    for r in ours:
        if r.get("Cheese"):
            alt.setdefault(norm(" ".join(r.get(k, "") for k in ("Cheese", "Product_Name", "Crust", "Size"))), []).append(r)
    alt_key = bool(alt)
    used: set[int] = set()
    seen: dict[str, int] = {}   # repeated names pair up by order of occurrence: 1st with 1st, 2nd with 2nd
    pairs: list[tuple[dict, dict | None]] = []
    for t in truth:
        key = norm(t["item_name"])
        n = seen[key] = seen.get(key, -1) + 1
        o = by_key.get(key, [])[n] if n < len(by_key.get(key, [])) else None
        if o is None and alt_key:   # Pearl Scan writes some names cheese first ("Standard Mozzarella - GF Cheese & Tomato - Small")
            o = next((r for r in alt.get(key, []) if id(r) not in used), None)
        if o is not None:
            used.add(id(o))
        pairs.append((t, o))
    # Second chance for names Pearl Scan shortened: the start of our name once notes are removed, on a row not yet used.
    for i, (t, o) in enumerate(pairs):
        if o is None and (t["item_name"], "*") not in errata:
            key = norm(t["item_name"])
            for r in ours:
                if id(r) not in used and norm(_clean(_full_name(r))).startswith(key):
                    used.add(id(r))
                    pairs[i] = (t, r)
                    break
    unmatched, mismatches, cells = [], [], 0
    for t, o in pairs:
        name = t["item_name"]
        if (name, "*") in errata:
            continue
        if o is None:
            unmatched.append(name)
            continue
        # Pearl Scan writes a row printed "per 100g" as a 100 g serving; we keep the printed basis.
        per100 = (t.get("servingsize") == "100" and t.get("servingsizeunit") in ("g", "ml")
                  and not o.get("Serving_Size") and any(k.endswith("_Per 100g/ml") and v for k, v in o.items())
                  and not any(k.endswith("_Per Portion") and v for k, v in o.items()))
        for gt_col, col in mapping.items():
            if per100 and not isinstance(col, list) and col in ("Serving_Size", "Serving_Size_Unit"):
                continue
            if per100 and isinstance(col, str) and col.endswith("_Per Portion"):
                col = col.replace("_Per Portion", "_Per 100g/ml")
            if col is None or gt_col not in t or gt_col == "item_name" or (name, gt_col) in errata:
                continue
            if isinstance(col, list) and not t[gt_col]:
                continue   # Pearl Scan filed a count under one of several neighbouring columns; check it where it did
            cells += 1
            ours_value = next((o[c] for c in col if o.get(c)), "") if isinstance(col, list) else o.get(col, "")
            if not same(t[gt_col], ours_value):
                mismatches.append(f"{name}.{gt_col}: Pearl Scan {t[gt_col]!r}, ours {ours_value!r}")
    checked = len(truth) - sum((t["item_name"], "*") in errata for t in truth)
    recall = (checked - len(unmatched)) / checked if checked else 1.0
    return {"rows": checked, "recall": recall, "cells": cells, "unmatched": unmatched, "mismatches": mismatches,
            "passed": recall >= ROW_RECALL_MIN and not mismatches}


def compare_golden(golden: list[dict], ours: list[dict]) -> list[str]:
    """Every golden row (matched on Product_Name + Category + Size) must exist with identical cells."""
    by_key: dict[tuple, list[dict]] = {}
    for r in ours:
        by_key.setdefault((r["Product_Name"], r["Category"], r.get("Size", "")), []).append(r)
    failures = []
    for g in golden:
        matches = by_key.get((g["Product_Name"], g["Category"], g.get("Size", "")))
        if matches is None:
            failures.append(f"missing row: {g['Product_Name']}{' ' + g['Size'] if g.get('Size') else ''} ({g['Category']})")
            continue
        for o in matches:   # rows sharing a key must all agree, or the golden row is checking only one of them
            for col, want in g.items():
                got = o.get(col, "" if want == "" else None)   # chain CSVs omit columns that are blank throughout
                if got is None:
                    failures.append(f"{g['Product_Name']}: column {col!r} not in output")
                elif not same(want, got):
                    failures.append(f"{g['Product_Name']}.{col}: expected {want!r}, got {got!r}")
    return failures

import csv
import re
from pathlib import Path

from pydantic import ValidationError

from pipeline.columns import PROVENANCE, Columns, build_row_model
from pipeline.validate import check_row, duplicate_issues


def _heading(category: str) -> list[str]:
    """A heading chain ("Buffet Sides - Buffet Pasta") as lower-case words without punctuation, one item per level."""
    return [re.sub(r"[^a-z0-9]", "", level.casefold()) for level in category.split(" - ") if level.strip()]


def _same_heading(a: str, b: str) -> bool:
    """The same heading up to punctuation ("Dine In" and "Dine-in"), or one is the other's parent heading (a chain cut short)."""
    x, y = _heading(a), _heading(b)
    short, long = sorted((x, y), key=len)
    return long[:len(short)] == short


def merge_by_key(rows: list[dict]) -> list[dict]:
    """One row per product where several sources describe it, only when it is very likely the same product: the same name, size and
    region, the same heading (`_same_heading`), no filled cell in both rows, and exactly one such partner on each side (a name
    printed twice, adult and kids, would be a guess and stays two rows). The merged row keeps the first row's cells and heading, its
    source_page becomes "first, second", flags are joined, and `notes` gets a "Merged product: ..." remark for data users."""
    def cells(row: dict) -> set[str]:
        return {k for k, v in row.items() if k not in PROVENANCE and k not in ("Product_Name", "Category", "Size") and v not in (None, "")}
    groups: dict[tuple, list[int]] = {}
    for i, row in enumerate(rows):
        groups.setdefault((row["Product_Name"], row.get("Size", ""), row.get("region", "")), []).append(i)
    partners: dict[int, list[int]] = {i: [] for i in range(len(rows))}
    for members in groups.values():
        for x in members:
            for y in members:
                if x < y and not cells(rows[x]) & cells(rows[y]) and _same_heading(rows[x].get("Category", ""), rows[y].get("Category", "")):
                    partners[x].append(y)
                    partners[y].append(x)
    merged_into: dict[int, int] = {}
    for x, ys in partners.items():
        if len(ys) == 1 and len(partners[ys[0]]) == 1 and x < ys[0]:
            merged_into[ys[0]] = x
    out: list[dict] = []
    index: dict[int, dict] = {}
    for i, row in enumerate(rows):
        if i not in merged_into:
            index[i] = dict(row)
            out.append(index[i])
            continue
        target = index[merged_into[i]]
        target |= {k: row[k] for k in cells(row)}
        target["flags"] = " | ".join(f for f in (target.get("flags"), row.get("flags")) if f)
        pages = [str(p) for p in (target.get("source_page"), row.get("source_page")) if p not in (None, "")]
        target["source_page"] = ", ".join(dict.fromkeys(pages))
        remark = f"Merged product: two source rows with the same name, size and heading (pages {target['source_page']})"
        if target.get("Category", "") != row.get("Category", ""):
            remark += f"; their headings were {target.get('Category', '')!r} and {row.get('Category', '')!r}"
        target["notes"] = "; ".join(n for n in (target.get("notes"), remark) if n)
    return out


def finalise(rows: list[dict], columns: Columns) -> list[dict]:
    """Check every row against the column dictionary and the arithmetic checks; record all issues in `flags`.

    Values are never changed: rows that fail keep what the source said so a reviewer can see it.
    """
    unknown = sorted({k for r in rows for k in r} - set(columns.types) - set(PROVENANCE))
    if unknown:   # a CSV can't carry it, so stop rather than drop the value
        raise ValueError(f"columns not in schemas/columns.yaml: {unknown}")
    model = build_row_model(columns)
    dupes = duplicate_issues(rows)
    out = []
    for i, row in enumerate(rows):
        data = {k: v for k, v in row.items() if k not in PROVENANCE and v not in (None, "")}
        issues = check_row(data)
        try:
            model.model_validate(data)
        except ValidationError as e:
            issues += [f"error: {'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
        if i in dupes:
            issues.append(dupes[i])
        flags = [row["flags"]] if row.get("flags") else []
        out.append(row | {"flags": " | ".join(flags + issues)})
    return out


def write_csv(rows: list[dict], columns: Columns, path: Path) -> list[str]:
    """Write one chain CSV with only the dictionary columns that have a value; returns the header."""
    used = [c for c in columns.types if c == "Product_Name" or any(r.get(c) not in (None, "") for r in rows)]
    header = used + PROVENANCE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        w.writerows({k: "" if v is None else v for k, v in r.items()} for r in rows)
    return header

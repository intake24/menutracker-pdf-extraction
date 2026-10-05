import csv
from pathlib import Path

from pydantic import ValidationError

from pipeline.columns import PROVENANCE, Columns, build_row_model
from pipeline.validate import check_row, duplicate_issues


def merge_by_key(rows: list[dict]) -> list[dict]:
    """One row per product where several sources describe it: rows with the same name, category, size and region whose filled
    cells do not overlap are merged into the first (its source_page stays; flags are joined). A row that shares a cell with the
    first, whether or not the values agree, stays a row of its own and is left to the duplicate check."""
    def cells(row: dict) -> set[str]:
        return {k for k, v in row.items() if k not in PROVENANCE and k not in ("Product_Name", "Category", "Size") and v not in (None, "")}
    out: list[dict] = []
    seen: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (row["Product_Name"], row.get("Category", ""), row.get("Size", ""), row.get("region", ""))
        target = next((r for r in seen.get(key, []) if not cells(r) & cells(row)), None)
        if target is None:
            row = dict(row)
            out.append(row)
            seen.setdefault(key, []).append(row)
            continue
        target |= {k: row[k] for k in cells(row)}
        target["flags"] = " | ".join(f for f in (target.get("flags"), row.get("flags")) if f)
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

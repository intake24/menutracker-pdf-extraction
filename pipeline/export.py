import csv
from pathlib import Path

from pydantic import ValidationError

from pipeline.columns import PROVENANCE, Columns, build_row_model
from pipeline.validate import check_row, duplicate_issues


def finalise(rows: list[dict], columns: Columns) -> list[dict]:
    """Check every row against the column dictionary and the arithmetic checks; record all issues in `flags`.

    Values are never changed: rows that fail keep what the source said so a reviewer can see it.
    """
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

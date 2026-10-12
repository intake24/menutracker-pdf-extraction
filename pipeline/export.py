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


COMMA_NUMBER = re.compile(r"(<\s?)?(\d+),(\d+)$")


def _clean_number(column: str, value: str) -> str:
    """The research team's rules for nutrient cells: a decimal comma becomes a point, and in kJ and kcal a comma followed by exactly
    three digits is a thousands comma and goes. Anything else (`1,2` kJ, a unit left in the cell) is left for the checks to flag."""
    if m := COMMA_NUMBER.match(value):
        sign, whole, rest = m.groups("")
        if not column.startswith(("energykCal", "energykJ")):
            return f"{sign}{whole}.{rest}"
        if len(rest) == 3 and len(whole) <= 3:
            return f"{sign}{whole}{rest}"
    return value


def strip_units(rows: list[dict], units: dict[str, str]) -> list[dict]:
    """Remove `g` or `mg` from the cells of a nutrient whose PDF column heading declares a unit ("Sodium (mg)": `108mg` is 108). `units` is a
    source option, nutrient -> unit (`{fibre: g, sodium: mg}`), for every basis of that nutrient. Only declared nutrients are touched. The
    number is not converted: when the cell's unit differs from the heading's, the flag says so. Each change is a `warn:`."""
    if not units:
        return rows
    out = []
    for row in rows:
        row, notes = dict(row), []
        for column, value in row.items():
            heading = units.get(column.split("_")[0])
            if heading and isinstance(value, str) and (m := re.fullmatch(r"((?:<\s?)?\d+(?:[.,]\d+)?)\s?(m?g)", value)):
                row[column] = m[1]
                differs = f" (the unit {m[2]} differs from the heading's {heading})" if m[2] != heading else ""
                notes.append(f"warn: normalised {column} '{value}' to '{m[1]}'{differs}")
        if notes:
            row["flags"] = " | ".join(filter(None, [row.get("flags"), *notes]))
        out.append(row)
    return out


def _clean_fraction(value: str) -> str:
    if m := re.fullmatch(r"(\d+)/(\d+)", value):
        return f"{int(m[1]) / int(m[2]):.2f}".rstrip("0").rstrip(".")
    return value


def normalise(row: dict, columns: Columns) -> tuple[dict, list[str]]:
    """The places where finalise changes a value: nutrient cells (see `_clean_number`) and Recommended_Portions (`1/2` is `0.5`); units are removed earlier, by `strip_units`.
    Every change is returned as a `warn:` so the original text stays on record."""
    row, notes = dict(row), []
    for column, value in row.items():
        if not isinstance(value, str):
            continue
        if columns.types.get(column) == "nutrient":
            new = _clean_number(column, value)
        elif column == "Recommended_Portions":
            new = _clean_fraction(value)
        else:
            continue
        if new != value:
            row[column] = new
            notes.append(f"warn: normalised {column} '{value}' to '{new}'")
    return row, notes


def drop_rows(rows: list[dict], names: list[str]) -> list[dict]:
    """Rows the research team does not want in the dataset (a swap that saves calories is a choice, not a food), by exact product name."""
    return [r for r in rows if r.get("Product_Name") not in names]


def finalise(rows: list[dict], columns: Columns) -> list[dict]:
    """Check every row against the column dictionary and the arithmetic checks; record all issues in `flags`.

    Values are kept as the source printed them, except the clean-ups in `normalise`, each of which is flagged.
    Rows that fail a check keep what the source said so a reviewer can see it.
    """
    unknown = sorted({k for r in rows for k in r} - set(columns.types) - set(PROVENANCE))
    if unknown:   # a CSV can't carry it, so stop rather than drop the value
        raise ValueError(f"columns not in schemas/columns.yaml: {unknown}")
    model = build_row_model(columns)
    dupes = duplicate_issues(rows)
    out = []
    for i, row in enumerate(rows):
        row, issues = normalise(row, columns)
        data = {k: v for k, v in row.items() if k not in PROVENANCE and v not in (None, "")}
        issues += check_row(data)
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

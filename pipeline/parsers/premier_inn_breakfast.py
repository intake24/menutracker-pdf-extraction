"""Premier Inn breakfast allergy & nutrition guide (served at Beefeater, Brewers Fayre, Table Table).

Each item is a block: name line, "Contains: ... May Contain: ..." (wrapping onto following lines in
either column), an "Energy ... Salt" header, then one per-portion nutrition line.
"""
import re
from pathlib import Path

from pipeline.allergens import UnknownAllergen, parse_allergens
from pipeline.ingest import page_texts

VALUE = r"(?:<\s?)?\d+(?:\.\d+)?|Negligible|Traces|Trace|Tr"   # as printed; see schemas/columns.yaml
NUTRITION = re.compile(
    rf"(?P<kj>\d+(?:\.\d+)?) kJ / (?P<kcal>\d+(?:\.\d+)?) kcal\s+(?P<fat>{VALUE}) g\s+(?P<sat>{VALUE}) g\s+"
    rf"(?P<carb>{VALUE}) g\s+(?P<sugar>{VALUE}) g\s+(?P<protein>{VALUE}) g\s+(?P<salt>{VALUE}) g"
)
ENERGY_VALUE = re.compile(r"\d+(?:\.\d+)?\s*kJ\b")   # any line with this must be a readable nutrition line
FIELDS = {"kj": "energykJ", "kcal": "energykCal", "fat": "fat", "sat": "saturates", "carb": "carbohydrates",
          "sugar": "sugars", "protein": "protein", "salt": "salt"}
DIET = re.compile(r"\s+-\s+(VE|V)\b.*$")   # " - VE      V" suffix (the trailing V is an icon)
AMOUNT = re.compile(r"\s*\(per (\d+(?:\.\d+)?)\s?(g|kg|ml|l|oz)\)")  # "(per 45g)" -> serving size
ITEM_INDENT = 4                            # headings are indented less than this, items more
TITLE = "PREMIER INN BREAKFAST"            # printed once on page 2; applies to every section


def _is_heading(text: str) -> bool:
    bare = re.sub(r"\(per [^)]*\)", "", text)
    return any(c.isalpha() for c in bare) and not any(c.islower() for c in bare)


def _split(line: str, col: int) -> tuple[str, str]:
    """Split a wrapped allergen line into its (contains, may contain) parts."""
    parts = re.split(r"\s{3,}", line.strip(), maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    indent = len(line) - len(line.lstrip())
    return ("", parts[0]) if indent >= col - 5 else (parts[0], "")


def _finish(item: dict, m: re.Match | None, page_no: int, unlisted: str) -> dict:
    line = item["name_line"]
    diet = DIET.search(line)
    name = DIET.sub("", line)
    amount = AMOUNT.search(name)
    row = {
        "Product_Name": AMOUNT.sub("", name).strip(),
        "Category": item["category"],
        "Serving_Size": amount.group(1) if amount else "",
        "Serving_Size_Unit": amount.group(2) if amount else "",
        "Diet": diet.group(1) if diet else "",
        "source_page": page_no,
    }
    try:
        row |= parse_allergens(" ".join(filter(None, item["contains"])), " ".join(filter(None, item["may"])),
                               unlisted)
    except UnknownAllergen as e:
        raise UnknownAllergen(f"{row['Product_Name']}: {e}") from e
    for cereal in ("spelt", "kamut"):   # the guide folds these into "Wheat", so it never declares them absent
        if row[cereal] == unlisted:
            row[cereal] = ""
    if m is None:
        row["flags"] = "error: no nutrition line found"
    else:
        row |= {f"{FIELDS[k]}_Per Portion": v for k, v in m.groupdict().items()}
    return row


def parse_pages(pages: list[str], unlisted: str) -> list[dict]:
    rows: list[dict] = []
    headings: list[str] = []   # current run of consecutive heading lines
    category = ""              # headings joined with " - "; a new run replaces it
    in_run = False
    item: dict | None = None   # item being read
    col: int | None = None     # column where "May Contain:" starts; set while reading allergen lines
    lines = [(page_no, line) for page_no, page in enumerate(pages, start=1) for line in page.splitlines()
             if line.strip() and not line.strip().startswith("Published on")]
    for i, (page_no, line) in enumerate(lines):
        text = line.strip()
        starts_item = i + 1 < len(lines) and lines[i + 1][1].strip().startswith("Contains:")
        heading = len(line) - len(line.lstrip()) < ITEM_INDENT and _is_heading(text)
        if text.startswith("Contains:"):
            col = line.index("May Contain:")
            item["contains"] = [line[:col].strip().removeprefix("Contains:").strip()]
            item["may"] = [line[col:].strip().removeprefix("May Contain:").strip()]
            continue
        if m := NUTRITION.search(line):
            rows.append(_finish(item, m, page_no, unlisted))
            item, col = None, None
            continue
        if ENERGY_VALUE.search(line):
            name = item["name_line"] if item else "?"
            raise ValueError(f"page {page_no}: unreadable nutrition line for {name!r}: {text!r}")
        if text.startswith(("Energy", "Per Portion:")):
            col = None
            continue
        if item is not None and col is not None and not starts_item and not heading:
            left, right = _split(line, col)
            item["contains"].append(left)
            item["may"].append(right)
            continue
        if item is not None and item["contains"]:   # previous item never got a nutrition line
            rows.append(_finish(item, None, page_no, unlisted))
            item, col = None, None
        if len(line) - len(line.lstrip()) < ITEM_INDENT:
            item = None   # an unfinished name before a heading is intro text, not an item
            if heading and text != TITLE:
                headings = (headings if in_run else []) + [DIET.sub("", text).strip()]
                category, in_run = " - ".join([TITLE, *headings]), True
            continue
        if item is not None and not item["contains"]:   # name wrapped onto a second line
            item["name_line"] += " " + text
        else:
            item = {"name_line": text, "category": category, "contains": [], "may": []}
        in_run = False
    if item is not None and item["contains"]:
        rows.append(_finish(item, None, len(pages), unlisted))
    return rows


def parse(pdf: Path, source: dict) -> list[dict]:
    return parse_pages(page_texts(pdf), source["markers"][""])

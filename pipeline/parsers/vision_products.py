"""Product pages read from page images: a title, a table of variants (crust and size) and allergen text blocks.

Used where each page is a product sheet (Papa John's): one `claude -p` call per listed page returns, for every table row,
the product name, the row label, the cells keyed by their printed header, and the allergen text that applies to that
row. The model only transcribes; code maps the headers to dictionary columns and the allergen text through the same
allergen vocabulary as every other parser. A header that is not in `header_columns` stops the run, so a new table layout
is noticed instead of guessed at.

Source options (config/chains.yaml):
  pages            pages to read, 1-based: numbers and "a-b" ranges (cover and text pages are left out)
  header_columns   printed header ("<table title> / <column header with unit>") -> dictionary column; "Column|unit"
                   also sets Serving_Size_Unit; "Column@Slice" also sets Portion_Type
  markers          {"": "No"} when the sheets list every ingredient allergen, so an unlisted one is absent
  instructions     what the pages look like
  dpi              render resolution (default 150)
Rows carry method "llm".
"""
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pipeline import llm
from pipeline.allergens import parse_allergens
from pipeline.parsers import vision_table

WORK = vision_table.WORK
RUNNER = llm.claude_runner          # tests replace these two
BUDGET = llm.Budget()

SCHEMA = {"type": "object", "required": ["rows"], "properties": {"rows": {"type": "array", "items": {
    "type": "object", "required": ["name", "values"], "properties": {
        "section": {"type": "string"}, "name": {"type": "string"}, "variant": {"type": "string"},
        "values": {"type": "object", "additionalProperties": {"type": "string"}},
        "contains": {"type": "string"}, "may": {"type": "string"}}}}}}


def expand_pages(spec: list) -> list[int]:
    pages = []
    for item in spec:
        if isinstance(item, int):
            pages.append(item)
        else:
            lo, hi = str(item).split("-")
            pages += range(int(lo), int(hi) + 1)
    return pages


def _target(spec: str) -> tuple[str, str, str]:
    """"Serving_Size|g" -> column, unit; "Portion_Size@Slice" -> column, portion type."""
    column, _, unit = spec.partition("|")
    column, _, kind = column.partition("@")
    return column, unit, kind


QUALIFIER = re.compile(r"\.?\s*With (.+?)\s*[–-]\s*(.+?) Only\s*$", re.I)


def _apply_qualifier(contains: str, variant: str) -> str:
    """'..., Soya. With Gluten Free Oats – Vegan Stuffed Crust Only': the extra allergen is for the named rows only."""
    m = QUALIFIER.search(contains)
    if not m:
        return contains
    base, extra, where = contains[:m.start()], m.group(1), m.group(2)
    where = re.sub(r"\bvegan\b", "", where, flags=re.I).strip().casefold()   # the sheet is already the vegan one
    if where and where in variant.casefold():
        free = re.match(r"(?i)gluten free (.+)", extra)
        return f"{base}, {free.group(1)} (Gluten Free)" if free else f"{base}, {extra}"
    return base


def check_answer(answer: dict, page_no: int) -> None:
    if not isinstance(answer.get("rows"), list) or not answer["rows"]:
        raise llm.LlmError(f"page {page_no}: the model returned no rows (list only table pages under `pages`)")


def rows_from_answer(answer: dict, source: dict, page_no: int) -> list[dict]:
    check_answer(answer, page_no)
    headers = {h.casefold(): c for h, c in source["header_columns"].items()}   # the model varies the case: "Kcal"/"kcal"
    unlisted = source.get("markers", {}).get("", "")
    rows = []
    for item in answer["rows"]:
        name = (item.get("name") or "").strip()
        if not name:
            raise llm.LlmError(f"page {page_no}: the model returned a row without a name: {item!r}")
        row = {"Product_Name": name, "Category": (item.get("section") or "").strip(), "source_page": page_no,
               "method": "llm"}
        if variant := (item.get("variant") or "").strip():
            row["Size"] = variant
        for header, value in item["values"].items():
            if header.casefold() not in headers:
                raise llm.LlmError(f"page {page_no}, {name}: header {header!r} is not in header_columns")
            column, unit, kind = _target(headers[header.casefold()])
            if value := value.strip():
                row[column] = value
                if unit:
                    row["Serving_Size_Unit"] = unit
                if kind:
                    row["Portion_Type"] = kind
        contains, may = _apply_qualifier((item.get("contains") or "").strip(), row.get("Size", "")), (item.get("may") or "").strip()
        if contains or may:
            row |= parse_allergens(contains, may, unlisted)
        rows.append(row)
    return rows


WORKERS = 3   # calls in flight at once


def page_rows(pdf: Path, source: dict, page_no: int) -> list[dict]:
    pages_dir = WORK / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    stem = pages_dir / f"{pdf.stem}-{page_no}"
    subprocess.run(["pdftoppm", "-r", str(source.get("dpi", 150)), "-f", str(page_no), "-l", str(page_no),
                    "-png", "-singlefile", str(pdf), str(stem)], check=True)
    png = stem.with_suffix(".png")
    prompt = (f"Read the image {png}. {source['instructions']} Return EVERY table row on the page, in order. "
              "values: an object whose keys are the printed column headers, each written as "
              "'<table title> / <column header> <unit>' (for example 'VALUES PER 100G / ENERGY kcal'), and whose "
              "values are the cells exactly as printed, as strings; leave out blank cells. contains and may: the "
              "allergen text printed for the base or dough that row belongs to, exactly as printed. Do not "
              "correct, convert or calculate anything.")
    answer = llm.call(prompt, SCHEMA, png, runner=RUNNER, cache_dir=WORK / "llm", budget=BUDGET,
                      validate=lambda a: check_answer(a, page_no))
    return rows_from_answer(answer, source, page_no)


def parse(pdf: Path, source: dict) -> list[dict]:
    pages = expand_pages(source["pages"])
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:   # results come back in page order
        return [row for rows in pool.map(lambda n: page_rows(pdf, source, n), pages) for row in rows]

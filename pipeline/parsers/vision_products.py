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
  variant_columns  true: the variant "Cheese - Crust - Size" is split on " - " into Cheese, Crust and Size (fewer parts: Cheese - Size, Size)
  figures_from_text  {columns, size_x0, size_order}: take every figure from the page's text layer (data lines, top to bottom) and use
                   the model only for the labels; the row counts and sizes must agree
  snap_labels      columns (e.g. [Product_Name, Crust]) whose model-read labels must be printed on the page; a near miss is replaced
                   by the printed text and flagged
  rules            printed warnings for some rows: {variant_has|section_has|name_has: text, may_contain: [columns]};
                   the columns become "May contain" unless they are already "Yes"
  markers          {"": "No"} when the sheets list every ingredient allergen, so an unlisted one is absent
  instructions     what the pages look like
  crops            {page: [band, ...]} in points: read each band of that page as its own image; a band is [top, bottom]
                   or a list of such strips stitched one under the other (column titles, then rows from further down)
  dpi              render resolution (default 150); crop_dpi {"<page>-<crop number>": dpi} overrides it for one band
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
BUDGET = llm.BUDGET                 # one budget for the whole run, shared with vision_table

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
    if not variant:
        raise llm.LlmError(f"allergen text with a qualifier on a row without a variant: {contains!r}")
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
        pending_may: list[str] = []
        if variant := (item.get("variant") or "").strip():
            if source.get("variant_columns"):   # "Standard Mozzarella - Classic Crust - Large": the last part is the size
                parts = [x.strip() for x in variant.split(" - ")]
                names = {1: ["Size"], 2: ["Cheese", "Size"], 3: ["Cheese", "Crust", "Size"]}.get(len(parts))
                if names is None:
                    raise llm.LlmError(f"page {page_no}, {name}: variant {variant!r} has {len(parts)} parts, expected 1 to 3")
                row |= dict(zip(names, parts))
            else:
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
        for rule in source.get("rules", []):   # printed warnings that apply to some rows ("Wheat Free base: traces of wheat")
            if any(rule[k].casefold() in (row.get(col) or "").casefold() for k, col in
                   (("variant_has", "Size"), ("section_has", "Category"), ("name_has", "Product_Name")) if k in rule):
                for column in rule["may_contain"]:
                    pending_may.append(column)
        contains, may = _apply_qualifier((item.get("contains") or "").strip(), row.get("Size", "")), (item.get("may") or "").strip()
        if contains or may:
            row |= parse_allergens(contains, may, unlisted)
        for column in pending_may:
            if row.get(column) in (None, "", "No"):
                row[column] = "May contain"
        rows.append(row)
    return rows


WORKERS = 3   # calls in flight at once


def page_rows(pdf: Path, source: dict, page_no: int, pages_dir: Path | None = None) -> list[dict]:
    """Rows of one page; with `crops` for the page, each band of it is read as its own image (a page with many small
    tables is too much for one answer)."""
    pages_dir = pages_dir or WORK / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    dpi = source.get("dpi", 150)
    bands = (source.get("crops") or {}).get(page_no) or [None]
    rows = []
    for i, band in enumerate(bands):
        dpi = (source.get("crop_dpi") or {}).get(f"{page_no}-{i + 1}", source.get("dpi", 150))   # small print: more pixels
        stem = pages_dir / (f"{pdf.stem}-{page_no}" + (f"-crop{i + 1}" if band else ""))
        png = Path(f"{stem}.png")
        strips = [band] if band and not isinstance(band[0], list) else (band or [None])   # a band may be several strips stitched
        images = []
        for k, strip in enumerate(strips):
            out = stem if len(strips) == 1 else stem.with_name(f"{stem.name}-strip{k}")
            cmd = ["pdftoppm", "-r", str(dpi), "-f", str(page_no), "-l", str(page_no), "-png", "-singlefile"]
            if strip:   # points from the top of the page, as pdftotext -bbox gives them
                top, bottom = (round(v * dpi / 72) for v in strip)
                cmd += ["-y", str(top), "-H", str(bottom - top)]
            subprocess.run(cmd + [str(pdf), str(out)], check=True)
            images.append(Path(f"{out}.png"))
        if len(images) > 1:   # e.g. the column titles of a table, then rows from further down it
            from PIL import Image
            pics = [Image.open(i) for i in images]
            sheet = Image.new("RGB", (max(p.width for p in pics), sum(p.height for p in pics)), "white")
            y = 0
            for pic in pics:
                sheet.paste(pic, (0, y))
                y += pic.height
            sheet.save(png)
        prompt = (f"Read the image {png}. {source['instructions']} Return EVERY table row on the page, in order. "
                  "values: an object whose keys are the printed column headers, each written as "
                  "'<table title> / <column header> <unit>' (for example 'VALUES PER 100G / ENERGY kcal'), and whose "
                  "values are the cells exactly as printed, as strings; leave out blank cells. contains and may: the "
                  "allergen text printed for the base or dough that row belongs to, exactly as printed. Do not "
                  "correct, convert or calculate anything.")
        answer = llm.call(prompt, SCHEMA, png, runner=RUNNER, cache_dir=WORK / "llm", budget=BUDGET,
                          validate=lambda a: check_answer(a, page_no))
        rows += rows_from_answer(answer, source, page_no)
    return rows


def pages_of(pdf: Path, source: dict) -> list[int]:
    return expand_pages(source["pages"])


def snap_labels(pdf: Path, page_no: int, rows: list[dict], columns: list[str]) -> list[dict]:
    """Labels the model read are checked against the page's text layer: one that is not there as printed is replaced by the
    closest run of printed words (and flagged), or the run stops if nothing is close."""
    import difflib

    from pipeline.ingest import page_words
    words = [w.text for w in page_words(pdf)[page_no - 1]]
    for row in rows:
        for column in columns:
            label = row.get(column)
            if not label:
                continue
            k = len(label.split())
            runs = {" ".join(words[i:i + k]): None for i in range(len(words) - k + 1)}
            if label in runs:
                continue
            close = difflib.get_close_matches(label, list(runs), 1, 0.85)
            if not close:
                raise llm.LlmError(f"page {page_no}: the label {label!r} is not printed on the page and nothing is close")
            row["flags"] = (row.get("flags", "") + f" | " if row.get("flags") else "") + f"warn: {column} read as {label!r}, printed as {close[0]!r}"
            row[column] = close[0]
    return rows


def with_text_figures(pdf: Path, source: dict, page_no: int, rows: list[dict]) -> list[dict]:
    """The model reads the labels; the figures come from the page's text layer, which is exact. Rows pair up in page order
    and each pair must agree on the size, or the run stops."""
    from pipeline.parsers.grouped_table import figure_lines
    spec = source["figures_from_text"]
    lines = figure_lines(pdf, page_no, spec["columns"], spec["size_x0"], spec["size_order"])
    if len(lines) != len(rows):
        raise llm.LlmError(f"page {page_no}: the model read {len(rows)} rows, the text layer has {len(lines)} data lines")
    for row, (size, figures) in zip(rows, lines):
        if row.get("Size", "").casefold() != size.casefold():
            raise llm.LlmError(f"page {page_no}, {row['Product_Name']}: the model's size {row.get('Size')!r} is not the text layer's {size!r}")
        for column in spec["columns"]:   # replace whatever the model read, and drop columns the model filled that the text lacks
            row[column] = figures[column]
    return rows


def parse(pdf: Path, source: dict) -> list[dict]:
    pages = pages_of(pdf, source)
    def one(n: int) -> list[dict]:
        rows = page_rows(pdf, source, n)
        if source.get("snap_labels"):
            rows = snap_labels(pdf, n, rows, source["snap_labels"])
        return with_text_figures(pdf, source, n, rows) if source.get("figures_from_text") else rows
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:   # results come back in page order
        return [row for rows in pool.map(one, pages) for row in rows]

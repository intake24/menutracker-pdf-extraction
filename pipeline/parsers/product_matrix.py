"""Product matrix: one band per product between thin horizontal rules; text columns (name, pack size, ingredients, storage)
and numeric columns (per 100g, per serving) at fixed positions. Used for Odeon's pre-packed product matrix.

Each product's band holds wrapped paragraphs in the text columns and its figures on one line. Words are assigned to a column
by their position; text columns are joined in reading order, numeric cells go to the nearest numeric column. A band with
text in its first column only is a section title. Anything the parser can't place (a number under no column, a band with
figures but no name) raises.

Source options (config/chains.yaml):
  text_columns     [{column: <dictionary column>, x0: <left edge in pt>}, ...] left to right; the first is the product name
  numeric_columns  [{column: <dictionary column>, x: <centre in pt>}, ...]
  serving_column   column whose cell "30g" is split into Serving_Size and Serving_Size_Unit; text that is not an amount
                   and a unit goes to Portion_Size (optional)
  header_height   the column-header lines extend this far (pt) below the word "Products" (default 9)
  keep_units      keep unit suffixes printed in figure cells ("22g", "498 kcal"); by default the column's own unit is dropped
  rule_min_width   a rectangle at least this wide and under 2 pt high is a row rule (default 600)
"""
import re
from pathlib import Path

import pdfplumber

from pipeline.ingest import page_words

NUMBER = re.compile(r"^<?\s?\d[\d.,/]*[a-zA-Z]*$|^(?:Negligible|Traces?|Tr|N/?A|-)$")   # a printed slip (1,5 or <0/1) is kept and flagged later
SERVING = re.compile(r"^(\d+(?:\.\d+)?)\s*([A-Za-z]+)\s*(\(.*\))?$")   # "30g", "8 sweets", "30g (5-6 servings per pack)"
LINE_GAP = 3
UNIT = re.compile(r"^(?:kj|kcal|k|cal|g|mg)$", re.I)   # a unit word printed after a figure
X_TOLERANCE = 12     # a numeric cell must be this close to a column centre


def _text(words: list[dict]) -> str:
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(w["top"] - lines[-1][0]["top"]) <= LINE_GAP:
            lines[-1].append(w)
        else:
            lines.append([w])
    return " ".join(w["text"] for line in lines for w in sorted(line, key=lambda w: w["x0"]))


def _row(band: list[dict], source: dict, page_no: int, top: float, section: str) -> tuple[dict | None, str, bool]:
    text_cols, num_cols = source["text_columns"], source["numeric_columns"]
    first = text_cols[0]["x0"]
    cells: dict[str, list[dict]] = {c["column"]: [] for c in text_cols}
    figures: dict[str, str] = {}
    numeric = sorted((w for w in band if w["x0"] >= num_cols[0]["x"] - X_TOLERANCE), key=lambda w: w["x0"])
    for w in band:
        if w["x0"] < num_cols[0]["x"] - X_TOLERANCE:
            if w["x0"] < first - 2:
                raise ValueError(f"page {page_no}: {w['text']!r} left of the first column")
            cells[[c for c in text_cols if c["x0"] - 2 <= w["x0"]][-1]["column"]].append(w)
    merged: list[dict] = []   # "not declared": a phrase standing where a figure would be is one cell, kept as printed
    for w in numeric:
        plain = lambda t: not NUMBER.match(t) and not UNIT.match(t) and t != "-"
        if (merged and plain(w["text"]) and plain(merged[-1]["text"]) and abs(w["top"] - merged[-1]["top"]) < LINE_GAP
                and w["x0"] - merged[-1]["x1"] < 5):
            merged[-1] = {**merged[-1], "x1": w["x1"], "text": merged[-1]["text"] + " " + w["text"]}
        else:
            merged.append(w)
    current = None
    for w in merged:
        if UNIT.match(w["text"]) and current is not None:   # "2087 KJ", "171 k cal": the unit printed after the figure
            figures[current] += w["text"] if source.get("keep_units") else ""
            continue
        centre = (w["x0"] + w["x1"]) / 2
        if not NUMBER.match(w["text"]) and not UNIT.match(w["text"]) and w["x0"] < num_cols[1]["x"] - X_TOLERANCE:
            # words of the serving-size text that run into the first figure column
            cells[text_cols[-1]["column"]].append(w)
            continue
        nearest = min(num_cols, key=lambda c: abs(c["x"] - centre))
        if abs(nearest["x"] - centre) > X_TOLERANCE or not (NUMBER.match(w["text"]) or w["text"].islower() and " " in w["text"]):
            raise ValueError(f"page {page_no}: {w['text']!r} at x={centre:.0f} is under no column")
        if nearest["column"] in figures:
            raise ValueError(f"page {page_no}: two cells in {nearest['column']!r} in the band at y={top}: "
                             f"{figures[nearest['column']]!r} and {w['text']!r}")
        # a unit glued to the figure ("22g") is the column's own unit; dropping it is not a conversion
        figures[nearest["column"]] = w["text"] if source.get("keep_units") else re.sub(r"(?<=\d)[a-zA-Z]+$", "", w["text"])
        current = nearest["column"]
    name = _text(cells[text_cols[0]["column"]])
    others = {c: _text(ws) for c, ws in cells.items() if c != text_cols[0]["column"]}
    if not figures and not any(others.values()):
        return None, name or section, True   # a title band: only the first column has text
    if not name:
        raise ValueError(f"page {page_no}: a product band without a name at y={top}")
    row = {"Product_Name": name, "Category": section, "source_page": page_no} | {c: v for c, v in others.items() if v}
    row |= figures
    if (col := source.get("serving_column")) and row.get(col):
        raw = row.pop(col)
        if m := SERVING.match(raw):
            row |= {"Serving_Size": m.group(1), "Serving_Size_Unit": m.group(2)}
            if m.group(3):
                row["notes"] = m.group(3).strip("()")   # "(5-6 servings per pack)"
        else:
            row["Portion_Size"] = raw                  # not an amount and unit: kept as printed
    return row, section, False


def parse_page(page, words: list[dict], source: dict, page_no: int, section: str) -> tuple[list[dict], str]:
    text_cols, num_cols = source["text_columns"], source["numeric_columns"]
    min_width = source.get("rule_min_width", 600)
    rules = sorted({round(r["top"], 1) for r in page.rects if r["x1"] - r["x0"] >= min_width and r["bottom"] - r["top"] < 2})
    first = text_cols[0]["x0"]
    label = next((w for w in words if w["text"] == "Products"), None)   # the header lines start level with this label
    header_bottom = label["top"] + source.get("header_height", 9) if label else 0
    numeric_x = num_cols[0]["x"] - X_TOLERANCE
    # Rotated margin labels ("IMPULSE ICES", "FRUIT HANG BAGS") are taller than wide; they name a group of rows, not a product.
    body = [w for w in words if w["top"] >= header_bottom and rules and rules[0] - 0.5 <= w["top"] < rules[-1]
            and not (len(w["text"]) > 2 and w["bottom"] - w["top"] > 2.2 * (w["x1"] - w["x0"]))]
    # A band between two rules with words in the first column only is a section title.
    titles: list[tuple[float, str]] = []
    in_title: set[int] = set()
    for top, bottom in zip(rules, rules[1:]):
        band = [w for w in body if top - 0.5 <= w["top"] < bottom]
        if band and all(w["x0"] < text_cols[1]["x0"] - 2 for w in band) and not any(NUMBER.match(w["text"]) for w in band):
            titles.append((top, _text(band)))
            in_title |= {id(w) for w in band}
    # Cells are vertically centred in their row and a paragraph can run past the row's rules, so words belong to the
    # product whose line of figures is nearest in height, not to the band they happen to sit in.
    rest = [w for w in body if id(w) not in in_title]
    # A line of prose running across the figure columns with no figure in it is a note ("you can select the links ..."),
    # not part of a product: leave it out.
    prose = {y for y in {round(w["top"]) for w in rest}
             if not any(NUMBER.match(w["text"]) for w in rest if round(w["top"]) == y and w["x0"] >= numeric_x)
             and sum(w["x0"] >= numeric_x for w in rest if round(w["top"]) == y) >= 6}
    rest = [w for w in rest if not (round(w["top"]) in prose and w["x0"] >= text_cols[-1]["x0"] - 5)]
    lines: list[float] = []
    for y in sorted({round(w["top"]) for w in rest if w["x0"] >= numeric_x and NUMBER.match(w["text"])}):
        if not lines or y - lines[-1] > LINE_GAP:
            lines.append(y)
    groups: list[list[dict]] = [[] for _ in lines]
    # A band with exactly one line of figures is that product's row: everything in it belongs to it. Words in other bands
    # (a paragraph that runs past its row, a band holding two products) go to the nearest line of figures.
    def line_of(y: float) -> int:
        return min(range(len(lines)), key=lambda i: abs(lines[i] - y))
    for top, bottom in zip(rules, rules[1:]):
        band = [w for w in rest if top - 0.5 <= w["top"] < bottom]
        inside = {i for i, y in enumerate(lines) if top - 0.5 <= y < bottom}
        for w in band:
            groups[next(iter(inside)) if len(inside) == 1 else line_of(w["top"])].append(w)
    rows = []
    for y, group in zip(lines, groups):
        section = next((t for top, t in reversed(titles) if top <= y), section)
        row, _, _ = _row(group, source, page_no, y, section)
        if row is not None:
            rows.append(row)
    if titles:
        section = titles[-1][1]
    return rows, section


def parse(pdf: Path, source: dict) -> list[dict]:
    rows, section = [], ""
    clean = page_words(pdf)   # poppler words: pdfplumber splits this PDF's bold names into single letters
    with pdfplumber.open(pdf) as doc:
        for n, page in enumerate(doc.pages, start=1):
            words = [{"x0": w.x0, "x1": w.x1, "top": w.y0, "bottom": w.y1, "text": w.text} for w in clean[n - 1]]
            found, section = parse_page(page, words, source, n, section)
            rows += found
    return rows

"""Dish tables with Yes/No diet cells and a mark under each allergen, read from the text layer (Pizza Hut pages 2-6).

The header labels are rotated text; pdfplumber returns each rotated word spelled backwards, stacked in a column, so a column's
label is the set of reversed words found in one run of x positions. A cell is matched to its column by x position, never by
counting. Rows are found by the diet cell of the left-most column (every row has one); the name is the text left of the
columns, wrapped lines joining the nearest row; centred text between rows is a section heading; a small text in an allergen
cell that starts with "<" and a digit ("<20ppm"; between two columns it raises) is kept in `notes` as "<Allergen label> <text>", and any other text printed on a row's
line in the allergen area ("Refer directly to the supplier ...") is kept in `notes` as printed. Headings in a row ("Drinks", "Soft Drinks") are one
category joined with " - ".

Source options (config/chains.yaml):
  labels   a word of the printed column label -> dictionary column (or a list of columns, each set from the one mark); columns
           whose name starts with "Suitable_for_" hold the Yes/No printed in the cell, the others hold a mark
  markers  mark -> "Yes" / "May contain"; a mark that is not listed raises
  pages    pages to read: numbers and "a-b" ranges
A column label that is not in `labels`, a diet cell that is not Yes or No, a mark with no row, text between rows that fits no row
(or a page without a header) raises. An unmarked cell stays blank (not stated).
"""
import re
import unicodedata
from pathlib import Path

import pdfplumber

LINE_GAP = 3        # words whose vertical centres are this close are on one line
COLUMN_SLACK = 5    # a cell's centre may lie this far outside its column's label (pt)
HEADER_GAP = 3      # rotated words further apart than this start another column
MAX_NAME_GAP = 16   # a name line is at most this far from its row's centre
MAX_MARK_GAP = 12   # a mark or note is at most this far from its row's centre
ROW_TEXT_GAP = 5    # other text this close to a row's centre is printed on the row (a heading is further off)
DIET = "Suitable_for_"
NOTE = re.compile(r"^<\d")


def _centre(w: dict) -> float:
    return (w["top"] + w["bottom"]) / 2


def _xc(w: dict) -> float:
    return (w["x0"] + w["x1"]) / 2


def _norm(text: str) -> str:
    return text.casefold().strip("()/.,")


def _columns(words: list[dict], source: dict, page_no: int) -> list[dict]:
    rotated = sorted((w for w in words if not w["upright"]), key=_xc)
    if not rotated:
        raise ValueError(f"page {page_no}: no rotated column header found")
    runs: list[list[dict]] = [[rotated[0]]]
    for w in rotated[1:]:
        if w["x0"] - max(v["x1"] for v in runs[-1]) > HEADER_GAP:
            runs.append([])
        runs[-1].append(w)
    labels = {_norm(k): v for k, v in source["labels"].items()}
    out = []
    for run in runs:
        text = [w["text"][::-1] for w in sorted(run, key=_xc)]
        keys = {_norm(t) for t in text if _norm(t) in labels}
        if len(keys) != 1:
            raise ValueError(f"page {page_no}: the column label {' '.join(text)!r} matches {len(keys)} entries of `labels`")
        key = next(iter(keys))
        target = labels[key]
        out.append({"x0": min(w["x0"] for w in run), "x1": max(w["x1"] for w in run), "bottom": max(w["bottom"] for w in run),
                    "columns": target if isinstance(target, list) else [target], "label": next(t for t in text if _norm(t) == key)})
    return out


def _lines(words: list[dict]) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (_centre(w), w["x0"])):
        if lines and _centre(w) - _centre(lines[-1][0]) <= LINE_GAP:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def parse_page(words: list[dict], source: dict, page_no: int) -> list[dict]:
    cols = _columns(words, source, page_no)
    first, header_bottom = cols[0], max(c["bottom"] for c in cols)
    markers = source["markers"]
    upright = [w for w in words if w["upright"] and w["top"] >= header_bottom - 2]

    def column_of(w: dict) -> dict | None:
        near = min(cols, key=lambda c: abs(_xc(w) - (c["x0"] + c["x1"]) / 2))
        return near if near["x0"] - COLUMN_SLACK <= _xc(w) <= near["x1"] + COLUMN_SLACK else None

    cell_area = [w for w in upright if _xc(w) >= first["x0"] - COLUMN_SLACK]
    anchors = [w for w in cell_area if column_of(w) is first]
    for w in anchors:
        if w["text"] not in ("Yes", "No"):
            raise ValueError(f"page {page_no}: the diet cell {w['text']!r} (y={_centre(w):.0f}) is not Yes or No")
    if not anchors:
        raise ValueError(f"page {page_no}: no table rows found")
    rows = [{"centre": _centre(w), "cells": [], "names": [], "texts": []} for w in sorted(anchors, key=_centre)]

    def nearest(centre: float) -> tuple[dict, float]:
        row = min(rows, key=lambda r: abs(r["centre"] - centre))
        return row, abs(row["centre"] - centre)

    heading_words = []
    last = max(r["centre"] for r in rows)
    for w in cell_area:
        col, text = column_of(w), w["text"]
        if _centre(w) > last + MAX_MARK_GAP and text not in markers and text not in ("Yes", "No"):
            continue   # the page footer
        if w in anchors:
            row, _ = nearest(_centre(w))
            row["cells"].append((first, text))
        elif col is not None and (text in ("Yes", "No") or text in markers or NOTE.match(text)):
            row, gap = nearest(_centre(w))
            if gap > MAX_MARK_GAP:
                raise ValueError(f"page {page_no}: {text!r} at y={_centre(w):.0f} has no row")
            row["cells"].append((col, text))
        elif col is None and NOTE.match(text):
            raise ValueError(f"page {page_no}: the note {text!r} at y={_centre(w):.0f} lies between columns")
        elif len(text) == 1 and unicodedata.category(text) == "So":   # a symbol that is not a listed mark ("&" is not one)
            raise ValueError(f"page {page_no}: unknown mark {text!r} at y={_centre(w):.0f}")
        else:
            row, gap = nearest(_centre(w))
            (row["texts"] if gap <= ROW_TEXT_GAP else heading_words).append(w)   # text on a row's line, else a heading
    name_area = _lines([w for w in upright if _xc(w) < first["x0"] - COLUMN_SLACK])
    heading_lines = _lines(heading_words)
    for k, hline in enumerate(heading_lines):   # a heading line can start left of the columns: those words are the heading's, not a name
        for nline in name_area:
            if abs(_centre(nline[0]) - _centre(hline[0])) <= LINE_GAP:
                heading_lines[k] = sorted(nline + hline, key=lambda w: w["x0"])
    taken = {id(w) for line in heading_lines for w in line}
    sections = []   # (y, text): headings in a row (no table row between them) make one category
    for line in heading_lines:
        centre, text = _centre(line[0]), " ".join(w["text"] for w in line)
        if sections and not any(sections[-1][0] < r["centre"] < centre for r in rows):
            sections[-1] = (centre, f"{sections[-1][1]} - {text}")
        else:
            sections.append((centre, text))
    for line in name_area:
        if id(line[0]) in taken:
            continue   # part of a heading
        centre = _centre(line[0])
        row, gap = nearest(centre)
        if gap <= MAX_NAME_GAP:
            row["names"].append((centre, " ".join(w["text"] for w in line)))
        elif centre < rows[0]["centre"] - MAX_NAME_GAP or centre > last + MAX_NAME_GAP:
            continue   # page furniture above the table or below it
        else:
            raise ValueError(f"page {page_no}: the text {' '.join(w['text'] for w in line)!r} fits no row")
    out = []
    for r in rows:
        if not r["names"]:
            raise ValueError(f"page {page_no}: the row at y={r['centre']:.0f} has no name")
        row = {"Product_Name": " ".join(t for _, t in sorted(r["names"])),
               "Category": next((t for c, t in reversed(sections) if c < r["centre"] - 1), ""), "source_page": page_no}
        notes = []
        for col, text in r["cells"]:
            targets = col["columns"]
            if all(t.startswith(DIET) for t in targets):
                row[targets[0]] = text
            elif text in markers:
                for t in targets:
                    row[t] = markers[text]
            elif NOTE.match(text):
                notes.append(f"{col['label']} {text}")
            else:   # Yes/No under an allergen column
                raise ValueError(f"page {page_no}, {row['Product_Name']}: {text!r} under the allergen column {col['label']!r}")
        if r["texts"]:
            notes.append(" ".join(w["text"] for w in sorted(r["texts"], key=lambda w: (round(_centre(w) / LINE_GAP), w["x0"]))))
        if notes:
            row["notes"] = "; ".join(notes)
        out.append(row)
    return out


def expand_pages(spec: list) -> list[int]:
    out: list[int] = []
    for item in spec:
        a, _, b = str(item).partition("-")
        out += range(int(a), int(b or a) + 1)
    return out


def parse(pdf: Path, source: dict) -> list[dict]:
    rows = []
    with pdfplumber.open(pdf) as doc:
        for n in expand_pages(source["pages"]):
            words = doc.pages[n - 1].extract_words(extra_attrs=["upright"], x_tolerance=1.5, y_tolerance=1)
            rows += parse_page(words, source, n)
    return rows

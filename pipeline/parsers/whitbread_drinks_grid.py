"""Whitbread pub drinks allergy guide (Beefeater, Brewers Fayre, Table Table): an allergen grid, no nutrition.

Pages 3+ hold a grid: item names on the left, one column per allergen with rotated header labels,
and a marker (e.g. "Y") in the cell when the allergen is present. Section headings are centred.
Columns are found from the x position of each header label, so marks are matched by position.
"""
import re
from pathlib import Path

from pipeline.allergens import ALLERGENS, UnknownAllergen
from pipeline.ingest import Word, page_words

LABELS = {"Wheat": "wheat", "Rye": "rye", "Barley": "barley", "Oat": "oats", "Soya": "soya", "Egg": "egg",
          "Milk": "milk", "Fish": "fish", "Crustacean": "crustacean", "Mollusc": "mollusc",
          "Sulphite": "sulphite", "Sesame": "sesame", "Celery": "celery", "Mustard": "mustard",
          "Peanut": "peanut", "Lupin": "lupin", "Nuts": "treeNuts", "Source": "treeNutSource"}
GRID_CEREALS = ["wheat", "rye", "barley", "oats"]   # the "Cereals Containing Gluten" column group
NAME_MAX_X = 240     # item names sit left of the first allergen column
COLUMN_TOLERANCE = 15
FOOTER = re.compile(r"^\d{2}/\d{2}/\d{4}$|^Page$")
NO_INFO = "LABEL FOR ALLERGENS"   # "... - SEE PACKAGING LABEL FOR ALLERGENS": the grid says nothing


def _lines(words: list[Word]) -> list[list[Word]]:
    rows: dict[int, list[Word]] = {}
    for w in words:
        rows.setdefault(round(w.y0), []).append(w)
    return [sorted(rows[y], key=lambda w: w.x0) for y in sorted(rows)]


def parse_pages(pages: list[list[Word]], markers: dict[str, str]) -> list[dict]:
    rows: list[dict] = []
    headings: list[str] = []
    category, in_run = "", False
    for page_no, words in enumerate(pages, start=1):
        labels = [w for w in words if w.text in LABELS]
        if not any(w.text == "Description" for w in words) or not labels:
            continue   # intro and key pages
        columns = {LABELS[w.text]: w.x0 for w in labels}
        top = max(w.y1 for w in labels)
        bottom = min((w.y0 for w in words if FOOTER.match(w.text)), default=float("inf"))
        for line in _lines([w for w in words if top < w.y0 < bottom]):
            if line[0].x0 > NAME_MAX_X:   # centred section heading
                text = " ".join(w.text for w in line)
                headings = (headings if in_run else []) + [text]
                # a "SEE ... LABEL FOR ALLERGENS" heading is a complete (empty) section: don't nest under it
                category, in_run = " - ".join(headings), NO_INFO not in text
                continue
            in_run = False
            row = {"Product_Name": " ".join(w.text for w in line if w.x0 < NAME_MAX_X),
                   "Category": category, "source_page": page_no}
            cells: dict[str, str] = {}
            for w in (w for w in line if w.x0 >= NAME_MAX_X):
                col, x = min(columns.items(), key=lambda c: abs(c[1] - w.x0))
                if abs(x - w.x0) > COLUMN_TOLERANCE:
                    raise ValueError(f"page {page_no}: {w.text!r} at x={w.x0:.0f} is under no allergen column")
                if col == "treeNutSource":
                    cells[col] = (cells.get(col, "") + " " + w.text).strip()
                elif w.text not in markers:
                    raise UnknownAllergen(f"page {page_no}, {row['Product_Name']}: unknown marker {w.text!r}")
                else:
                    cells[col] = markers[w.text]
            blank = "" if NO_INFO in category else markers[""]
            row |= {a: cells.get(a, blank if a in columns else "") for a in ALLERGENS}
            cereals = [row[c] for c in GRID_CEREALS]
            row["gluten"] = "Yes" if "Yes" in cereals else ("No" if set(cereals) == {"No"} else "")
            if "treeNutSource" in cells:
                row["treeNutSource"] = cells["treeNutSource"]
            rows.append(row)
    return rows


def parse(pdf: Path, source: dict) -> list[dict]:
    return parse_pages(page_words(pdf), source["markers"])

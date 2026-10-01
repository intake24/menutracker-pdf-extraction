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
MARK_SLACK = 2       # a mark's centre must fall within its label's x-span, +/- this
LINE_GAP = 3         # words whose vertical centres are this close are on the same line (lines are ~9pt apart)
HEADER_SLACK = 15    # column labels sit within this distance below the "Product Description" header
FOOTER = re.compile(r"^\d{2}/\d{2}/\d{4}$|^Page$")
FOOTER_BAND = 0.9    # footer words only count in the bottom 10% of the page
NO_INFO = "LABEL FOR ALLERGENS"   # "... - SEE PACKAGING LABEL FOR ALLERGENS": the grid says nothing
ALLERGEN_WORDS = ("ALLERGEN", "PACKAGING", "LABEL")   # any other heading with these is unknown wording


def _lines(words: list[Word]) -> list[list[Word]]:
    """Group words into lines by vertical centre, so sub-point offsets between a name and its marks don't split them."""
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (w.y0 + w.y1) / 2):
        centre = (w.y0 + w.y1) / 2
        if lines and centre - (lines[-1][0].y0 + lines[-1][0].y1) / 2 <= LINE_GAP:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w.x0) for line in lines]


def _column(columns: dict[str, Word], w: Word, page_no: int) -> str:
    centre = (w.x0 + w.x1) / 2
    for col, label in columns.items():
        if label.x0 - MARK_SLACK <= centre <= label.x1 + MARK_SLACK:
            return col
    raise ValueError(f"page {page_no}: {w.text!r} at x={w.x0:.0f} is under no allergen column")


def parse_pages(pages: list[list[Word]], markers: dict[str, str]) -> list[dict]:
    rows: list[dict] = []
    headings: list[str] = []
    category, in_run = "", False
    for page_no, words in enumerate(pages, start=1):
        header = [w for w in words if w.text in ("Description", "Product")]
        if not header:
            continue   # intro and key pages
        band = max(w.y1 for w in header) + HEADER_SLACK
        labels = [w for w in words if w.text in LABELS and w.x0 >= NAME_MAX_X and w.y0 < band]
        if len({w.text for w in labels}) != len(labels):
            raise ValueError(f"page {page_no}: an allergen column label appears twice in the header")
        columns = {LABELS[w.text]: w for w in labels}
        top = max(w.y1 for w in labels)
        page_bottom = max(w.y1 for w in words)
        bottom = min((w.y0 for w in words if FOOTER.match(w.text) and w.y0 > FOOTER_BAND * page_bottom),
                     default=float("inf"))
        for line in _lines([w for w in words if top < w.y0 < bottom]):
            if all(w.text in markers for w in line):
                raise ValueError(f"page {page_no}: marker line {[w.text for w in line]} has no item name")
            if line[0].x0 > NAME_MAX_X:   # centred section heading
                text = " ".join(w.text for w in line)
                if any(k in text for k in ALLERGEN_WORDS) and NO_INFO not in text:
                    raise ValueError(f"page {page_no}: unrecognised allergen heading {text!r}")
                headings = (headings if in_run else []) + [text]
                # a "SEE ... LABEL FOR ALLERGENS" heading is a complete (empty) section: don't nest under it
                category, in_run = " - ".join(headings), NO_INFO not in text
                continue
            in_run = False
            row = {"Product_Name": " ".join(w.text for w in line if w.x0 < NAME_MAX_X),
                   "Category": category, "source_page": page_no}
            cells: dict[str, str] = {}
            for w in (w for w in line if w.x0 >= NAME_MAX_X):
                col = _column(columns, w, page_no)
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

"""Generic parser for "item name followed by a row of numbers" nutrition tables (Five Guys, Pizza Express, ...).

Columns are found by position: on each page the right edges of the numeric cells are clustered into
columns, and `source["columns"]` names them left to right. Position (not token count) is what keeps a
row with blank cells, e.g. an item with per-100g values only, in the right columns.
"""
import re
from collections import Counter
from pathlib import Path

from pipeline.ingest import Word, page_words

NUMBER = re.compile(r"^(?:<\s?)?\d+(?:\.\d+)?$|^(?:Negligible|Traces?|Tr)$")
MIN_NUMBERS = 3          # a line needs this many trailing numeric cells to be a data row
SECTION_INDENT = 12      # section headings start at the left margin; wrapped text and notes are indented more
LINE_GAP = 3             # words whose vertical centres are this close are on one line
COLUMN_GAP = 9           # right edges further apart than this (pt) belong to different columns


def _lines(words: list[Word]) -> list[list[Word]]:
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (w.y0 + w.y1) / 2):
        centre = (w.y0 + w.y1) / 2
        if lines and centre - (lines[-1][0].y0 + lines[-1][0].y1) / 2 <= LINE_GAP:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w.x0) for line in lines]


def _split(line: list[Word]) -> tuple[list[Word], list[Word]]:
    """(name words, trailing numeric cells)."""
    cut = len(line)
    while cut > 0 and NUMBER.match(line[cut - 1].text):
        cut -= 1
    return line[:cut], line[cut:]


def _heading(line: list[Word], left: float) -> str | None:
    """Section heading text: a leading run of ALL-CAPS words at the left margin, followed by nothing or a "- note"."""
    if line[0].x0 - left >= SECTION_INDENT:
        return None
    words = []
    for w in line:
        letters = [c for c in w.text if c.isalpha()]
        if not letters or not all(c.isupper() for c in letters):
            break
        words.append(w.text)
    rest = line[len(words):]
    if not words or (rest and rest[0].text != "-") or any(c.isdigit() for w in line[:len(words)] for c in w.text):
        return None
    return " ".join(words)


def _anchors(cells: list[Word]) -> list[float]:
    edges = sorted(w.x1 for w in cells)
    clusters = [[edges[0]]]
    for x in edges[1:]:
        if x - clusters[-1][-1] > COLUMN_GAP:
            clusters.append([])
        clusters[-1].append(x)
    return [sum(c) / len(c) for c in clusters]


def parse_pages(pages: list[list[Word]], columns: list[str]) -> list[dict]:
    rows = []
    category = ""
    for page_no, words in enumerate(pages, start=1):
        lines = _lines(words)
        split = [_split(line) for line in lines]
        data = [(name, cells) for name, cells in split if name and len(cells) >= MIN_NUMBERS]
        if not data:
            continue
        # Columns come from the most common row width, so a name that ends in a number
        # ("Peroni Nastro Azzurro 0.0") or a row with blank cells can't create or hide a column.
        usual = Counter(len(cells) for _, cells in data).most_common(1)[0][0]
        anchors = _anchors([c for _, cells in data if len(cells) == usual for c in cells])
        if len(anchors) != len(columns):
            raise ValueError(f"page {page_no}: found {len(anchors)} numeric columns, config names {len(columns)}")
        left = min(name[0].x0 for name, _ in data)
        for line, (name, cells) in zip(lines, split):
            if not (name and len(cells) >= MIN_NUMBERS):
                if not cells and (heading := _heading(line, left)):
                    category = heading
                continue
            while cells and cells[0].x1 < anchors[0] - COLUMN_GAP:   # left of the first column: part of the name
                name, cells = name + cells[:1], cells[1:]
            row = {"Product_Name": " ".join(w.text for w in name), "Category": category, "source_page": page_no}
            for w in cells:
                col = columns[min(range(len(anchors)), key=lambda i: abs(anchors[i] - w.x1))]
                row[col] = w.text
            rows.append(row)
    return rows


def parse(pdf: Path, source: dict) -> list[dict]:
    return parse_pages(page_words(pdf), source["columns"])

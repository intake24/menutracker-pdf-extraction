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
VALUELIKE = re.compile(r"\d|^(?:-|–|N/?A)$", re.I)   # a token that looks like a cell value, readable or not
NOTE_START = ("-", "*", "†")                          # a line starting like this is a note, not a name
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
        found = [(name, cells) for name, cells in map(_split, lines) if name and len(cells) >= MIN_NUMBERS]
        if not found:
            continue
        # Columns come from the most common row width, so a row with blank cells can't create or hide a column.
        usual = Counter(len(cells) for _, cells in found).most_common(1)[0][0]
        anchors = _anchors([c for _, cells in found if len(cells) == usual for c in cells])
        if len(anchors) != len(columns):
            raise ValueError(f"page {page_no}: found {len(anchors)} numeric columns, config names {len(columns)}")
        edge = anchors[0] - COLUMN_GAP                        # words wholly left of this are the name
        left = min(name[0].x0 for name, _ in found)
        # Classify every line by position: a data row has at least MIN_NUMBERS value-like words in the columns.
        kinds = []
        for line in lines:
            cells = [w for w in line if w.x1 >= edge]
            kinds.append("data" if sum(bool(VALUELIKE.search(w.text)) for w in cells) >= MIN_NUMBERS else "other")
        first_row = kinds.index("data")
        last_row = max(i for i, kind in enumerate(kinds) if kind == "data")
        start = first_row   # the table starts at the headings and notes directly above its first row
        while start > 0 and kinds[start - 1] == "other" and (
                _heading(lines[start - 1], left) or " ".join(w.text for w in lines[start - 1]).startswith(NOTE_START)):
            start -= 1
        for i, (line, kind) in enumerate(zip(lines, kinds)):
            if i < start:
                continue   # page title, column headers
            text = " ".join(w.text for w in line)
            if kind == "other":
                if heading := _heading(line, left):
                    category = heading
                elif i < last_row and not text.startswith(NOTE_START):
                    raise ValueError(f"page {page_no}: text between rows that is not a heading or note "
                                     f"(a wrapped name?): {text!r}")
                continue
            name = [w for w in line if w.x1 < edge]
            cells = [w for w in line if w.x1 >= edge]
            if not name:
                raise ValueError(f"page {page_no}: numbers without a name: {text!r}")
            product = " ".join(w.text for w in name)
            row = {"Product_Name": product, "Category": category, "source_page": page_no}
            for w in cells:
                if not NUMBER.match(w.text):
                    raise ValueError(f"page {page_no}: unreadable cell {w.text!r} in row {product!r}")
                nearest = min(range(len(anchors)), key=lambda j: abs(anchors[j] - w.x1))
                if abs(anchors[nearest] - w.x1) > COLUMN_GAP:
                    raise ValueError(f"page {page_no}: {w.text!r} in row {product!r} is under no column")
                if columns[nearest] in row:
                    raise ValueError(f"page {page_no}: two cells in column {columns[nearest]!r} in row {product!r}")
                row[columns[nearest]] = w.text
            rows.append(row)
    return rows


def parse(pdf: Path, source: dict) -> list[dict]:
    return parse_pages(page_words(pdf), source["columns"])

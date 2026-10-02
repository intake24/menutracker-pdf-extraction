"""Generic parser for "item name followed by a row of numbers" nutrition tables (Five Guys, Pizza Express, ...).

Columns are found by position, not by counting tokens: the right edges of a table's numeric cells are clustered
into columns and `source["columns"]` names them left to right. That keeps a row with blank cells, e.g. an item with
per-100g values only, in the right columns. Words come from pdfplumber, which separates cells that are printed
almost touching (`1232` and `11.1`) where poppler returns one word.

Source options (config/chains.yaml):
  columns        the dictionary column of each numeric column, left to right (required)
  header         a word that marks a column-header line, e.g. "Energy". Enables several tables per page, each with
                 its own columns, and takes the section name from the header block (the text left of the columns)
  text_values    words that may stand in a cell ("Portion", "Piece"); allowed only under a column that has no basis
  furniture      lines above a table header that are page furniture, not a title (running heads); ignored
  name_amount    a trailing amount in the name ("BBQ Dip 25g") becomes Serving_Size and Serving_Size_Unit
  text_flow      read words in drawing order and keep rows printed over each other apart (an Odeon PDF defect)
  invalid_values cell values that are errors in the source ("#N/A"); kept as printed, the row is flagged
  name_below     a line of only numbers followed by a line of only text: the text is that row's name
  free_sections  name-only text that is not a wrapped name is a sub-section label; without wrapped_names, all of it is
  wrapped_names  join a name-only line directly above a data row onto that row's name
  titles         page titles allowed above a table header, e.g. "Breakfast (selected restaurants only)"; each
                 persists as a parent in Category until the next one. Any other text there raises.

Without `header`, sections are ALL-CAPS heading lines at the left margin. Anything the parser can't place, an
unreadable cell, a cell under no column, text between rows, raises instead of being guessed at.
"""
import re
from collections import Counter
from pathlib import Path

from pipeline.ingest import Word, page_words_fine

NUMBER = re.compile(r"^(?:<\s?)?\d+(?:\.\d+)?$|^(?:Negligible|Traces?|Tr)$")
AMOUNT = re.compile(r"^(.*?\S)(?:\s+-\s*|\s+)(\d+(?:\.\d+)?)\s?(g|ml|cl|oz)(\s+[-*A-Za-z(].*)?$")
BRACKET_AMOUNT = re.compile(r"\([^)]*?(\d+(?:\.\d+)?)\s?(g|ml|cl|oz)\b[^)]*\)")   # "(Per Portion of 10g)", "(16oz as served)"
MIN_NUMBERS = 3          # a line needs this many trailing numeric cells to be a data row
SECTION_INDENT = 12      # section headings start at the left margin; wrapped text and notes are indented more
VALUELIKE = re.compile(r"\d|^(?:-|–|#?N/?A)$", re.I)   # a token that looks like a cell value, readable or not
NOTE_START = ("-", "*", "†")                          # a line starting like this is a note, not a name
LINE_GAP = 3             # words whose vertical centres are this close are on one line
WRAP_LINES = 1.5         # a name-only line within this many line heights above a data row continues its name
TABLE_GAP = 20           # without header lines: last-cell right edges further apart than this are different tables
COLUMN_GAP = 9           # right edges further apart than this (pt) belong to different columns


def _lines(words: list[Word]) -> list[list[Word]]:
    """Group words into lines by vertical centre; words of different layers (rows printed over each other) never
    share a line."""
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: ((w.y0 + w.y1) / 2, w.layer)):
        centre = (w.y0 + w.y1) / 2
        for line in reversed(lines[-3:]):
            if line[0].layer == w.layer and centre - (line[0].y0 + line[0].y1) / 2 <= LINE_GAP:
                line.append(w)
                break
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w.x0) for line in lines]


def _is_ruler(line: list[Word]) -> bool:
    """Column numbers printed above a table (4 5 6 7 ...): consecutive integers and nothing else."""
    try:
        n = [int(w.text) for w in line]
    except ValueError:
        return False
    return len(n) >= MIN_NUMBERS and n == list(range(n[0], n[0] + len(n)))


def _names_from_below(lines: list[list[Word]], number: re.Pattern) -> list[list[Word]]:
    """A line of only numbers followed by a line of only text: the text is that row's name, printed under it."""
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if (nxt and len(line) >= MIN_NUMBERS and all(number.match(w.text) for w in line)
                and not any(number.match(w.text) for w in nxt) and nxt[0].y0 - line[0].y1 < 2 * (line[0].y1 - line[0].y0)):
            dy = (line[0].y0 + line[0].y1) / 2 - (nxt[0].y0 + nxt[0].y1) / 2
            out.append(sorted([w._replace(y0=w.y0 + dy, y1=w.y1 + dy) for w in nxt] + line, key=lambda w: w.x0))
            i += 2
        else:
            out.append(line)
            i += 1
    return out


def _split(line: list[Word], number: re.Pattern) -> tuple[list[Word], list[Word]]:
    """(name words, trailing numeric cells)."""
    cut = len(line)
    while cut > 0 and number.match(line[cut - 1].text):
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


def _tables(found: list[tuple[int, list[Word]]], header_lines: list[int]) -> list[list[tuple[int, list[Word]]]]:
    """Split the data rows into tables: by the header lines before them, or, without headers, by where their
    last cell ends (the rows of one table end at the same x)."""
    if header_lines:
        by_header: dict[int, list] = {}
        for item in found:
            by_header.setdefault(sum(h < item[0] for h in header_lines), []).append(item)
        return list(by_header.values())
    ordered = sorted(found, key=lambda f: f[1][-1].x1)
    groups = [[ordered[0]]]
    for item in ordered[1:]:
        if item[1][-1].x1 - groups[-1][-1][1][-1].x1 > TABLE_GAP:
            groups.append([])
        groups[-1].append(item)
    return groups


def _classify(lines: list[list[Word]], tables: list[list[float]], table_of: dict[int, list[float]],
              header_lines: list[int]) -> list[list[float] | None]:
    """For each line: the column anchors of its table if it is a data row (at least MIN_NUMBERS value-like words
    in that table's columns), else None."""
    kinds = []
    for i, line in enumerate(lines):
        n = sum(h < i for h in header_lines)
        candidates = [table_of[n]] if header_lines and n in table_of else tables
        best = None
        for anchors in candidates:
            cells = [w for w in line if w.x1 >= anchors[0] - COLUMN_GAP]
            if (sum(bool(VALUELIKE.search(w.text)) for w in cells) >= MIN_NUMBERS
                    and cells[-1].x1 <= anchors[-1] + COLUMN_GAP
                    and (best is None or abs(cells[-1].x1 - anchors[-1]) < abs(cells[-1].x1 - best[-1]))):
                best = anchors
        kinds.append(best)
    return kinds


def _row(line: list[Word], lead: list[Word], anchors: list[float], columns: list[str], category: str,
         page_no: int, number: re.Pattern = NUMBER, name_amount: bool = False,
         anywhere: re.Pattern = NUMBER) -> dict:
    edge = anchors[0] - COLUMN_GAP                         # words wholly left of this are the name
    name = [w for w in line if w.x1 < edge]
    if not name:
        raise ValueError(f"page {page_no}: numbers without a name: {' '.join(w.text for w in line)!r}")
    product = " ".join(w.text for w in lead + name)
    if sum(bool(number.match(w.text)) for w in name) >= MIN_NUMBERS:
        raise ValueError(f"page {page_no}: name contains numbers, so the row's columns don't match the config: "
                         f"{product!r}")
    row = {"Product_Name": product, "Category": category, "source_page": page_no}
    if name_amount and (m := AMOUNT.match(product)):   # "BBQ Dip 25g": the amount is the serving size
        row |= {"Product_Name": m.group(1) + (m.group(4) or ""), "Serving_Size": m.group(2), "Serving_Size_Unit": m.group(3)}
    elif name_amount and (m := BRACKET_AMOUNT.search(product)):   # the name stays as printed; the amount is the serving size
        row |= {"Serving_Size": m.group(1), "Serving_Size_Unit": m.group(2)}
    for w in (w for w in line if w.x1 >= edge):
        if not number.match(w.text):
            raise ValueError(f"page {page_no}: unreadable cell {w.text!r} in row {product!r}")
        nearest = min(range(len(anchors)), key=lambda j: abs(anchors[j] - w.x1))
        if not anywhere.match(w.text) and "_Per " in columns[nearest]:
            raise ValueError(f"page {page_no}: the word {w.text!r} in row {product!r} is under the nutrient column "
                             f"{columns[nearest]!r}")
        if abs(anchors[nearest] - w.x1) > COLUMN_GAP:
            raise ValueError(f"page {page_no}: {w.text!r} in row {product!r} is under no column")
        if columns[nearest] in row:
            raise ValueError(f"page {page_no}: two cells in column {columns[nearest]!r} in row {product!r}")
        row[columns[nearest]] = w.text
    return row


def parse_pages(pages: list[list[Word]], columns: list[str], header: str | None = None,
                wrapped_names: bool = False, titles: list[str] = (), text_values: list[str] = (), furniture: list[str] = (), name_amount: bool = False, free_sections: bool = False, invalid_values: list[str] = (), name_below: bool = False) -> list[dict]:
    def extend(words):
        return re.compile(NUMBER.pattern + "|^(?:" + "|".join(map(re.escape, words)) + ")$") if words else NUMBER
    number = extend([*text_values, *invalid_values])
    anywhere = extend(invalid_values)   # may stand under a nutrient column: kept as printed and flagged downstream
    rows = []
    parent = section = ""   # parent: a page title that persists ("Breakfast (selected restaurants only)")
    for page_no, words in enumerate(pages, start=1):
        lines = [l for l in _lines(words) if not _is_ruler(l)]
        if name_below:
            lines = _names_from_below(lines, number)
        split = [_split(line, number) for line in lines]
        found = [(i, cells) for i, (name, cells) in enumerate(split) if name and len(cells) >= MIN_NUMBERS]
        if not found:
            continue
        # A header line has the header word and no data cells: a product called "Energy Bar" is a row.
        header_lines = [i for i, line in enumerate(lines)
                        if header and any(w.text == header for w in line) and len(split[i][1]) < MIN_NUMBERS]
        # One set of columns per table, from the table's most common row width, so a row with blank cells
        # can't create or hide a column.
        tables: list[list[float]] = []
        table_of: dict[int, list[float]] = {}   # number of header lines before the table -> its column anchors
        for group in _tables(found, header_lines):
            usual = Counter(len(cells) for _, cells in group).most_common(1)[0][0]
            anchors = _anchors([c for _, cells in group if len(cells) == usual for c in cells])
            if len(anchors) != len(columns):
                raise ValueError(f"page {page_no}: found {len(anchors)} numeric columns, config names {len(columns)}")
            tables.append(anchors)
            table_of[sum(h < group[0][0] for h in header_lines)] = anchors
        kinds = _classify(lines, tables, table_of, header_lines)
        data = [i for i, anchors in enumerate(kinds) if anchors]
        if not data:
            raise ValueError(f"page {page_no}: rows with numbers were found but none fit the table's columns")
        first_row, last_row = data[0], data[-1]
        left = min(split[i][0][0].x0 for i, _ in found)

        # Where the table starts: at its first header line, else at the headings and notes directly above its
        # first row. Anything earlier is page furniture.
        start = first_row
        if header_lines and header_lines[0] < first_row:
            start = header_lines[0]
            above = [" ".join(w.text for w in line) for line in lines[:start]]
            above = [a for a in above if not any(c.isdigit() for c in a) and a not in furniture]   # "PER PORTION PER 100g" is not a title
            if unknown := [a for a in above if a not in titles]:
                raise ValueError(f"page {page_no}: unrecognised text above the table header {unknown[0]!r}; "
                                 f"list it under `titles` if it is a page title")
            parent = " ".join(above) or parent
        else:
            while start > 0 and kinds[start - 1] is None and (
                    _heading(lines[start - 1], left) or " ".join(w.text for w in lines[start - 1]).startswith(NOTE_START)):
                start -= 1

        in_header = False
        block: list[list[Word]] = []     # lines of the current column-header block
        pending: list[list[Word]] = []   # name-only lines waiting for the data row they continue
        for i in range(start, len(lines)):
            line, anchors = lines[i], kinds[i]
            text = " ".join(w.text for w in line)
            if i in header_lines:
                block = block if in_header else []
                block.append(line)
                in_header, pending = True, []   # a title above a column header ("PER PORTION PER 100g") is not a name
            elif anchors is None:
                if in_header:
                    block.append(line)
                elif heading := _heading(line, left):
                    section = heading
                elif i < last_row and not text.startswith(NOTE_START):
                    if not wrapped_names and not free_sections:
                        raise ValueError(f"page {page_no}: text between rows that is not a heading or note "
                                         f"(a wrapped name?): {text!r}")
                    pending.append(line)
            else:
                if in_header:
                    # The section name is the header-block text left of the numeric columns, level with the
                    # column headers. Text below the last column header is the start of this row's name.
                    edge = anchors[0] - 2 * COLUMN_GAP
                    bottom = max(w.y1 for l in block for w in l if w.x1 >= edge)
                    above = [l for l in block if l[0].y0 < bottom]
                    left_text = " ".join(w.text for l in above for w in l if w.x1 < edge)
                    section = ("" if left_text in furniture else left_text) or section
                    pending = [l for l in block if l[0].y0 >= bottom]
                    in_header = False
                    if pending and not wrapped_names:
                        raise ValueError(f"page {page_no}: text between the column headers and the first row "
                                         f"(a wrapped name?): {' '.join(w.text for w in pending[0])!r}")
                lead: list[Word] = []
                if pending and free_sections:
                    # Name-only lines directly above the row (and not reaching into the columns) are its wrapped
                    # name; any line before them is a sub-section label that applies from here on.
                    below, keep = line, []
                    while pending and wrapped_names and (below[0].y0 - pending[-1][0].y0 <= WRAP_LINES * (below[0].y1 - below[0].y0)
                                       and not any(w.x1 >= anchors[0] - COLUMN_GAP for w in pending[-1])):
                        keep.insert(0, pending.pop())
                        below = keep[0]
                    if pending:
                        section = " - ".join(" ".join(w.text for w in l) for l in pending)
                    lead, pending = [w for l in keep for w in l], []
                elif pending:
                    if line[0].y0 - pending[-1][0].y0 > WRAP_LINES * (line[0].y1 - line[0].y0):
                        raise ValueError(f"page {page_no}: text above a row is too far away to be a wrapped name: "
                                         f"{' '.join(w.text for w in pending[-1])!r}")
                    lead, pending = [w for l in pending for w in l], []
                    if any(w.x1 >= anchors[0] - COLUMN_GAP for w in lead):
                        raise ValueError(f"page {page_no}: text above a row reaches into the columns, so it is not "
                                         f"a name: {' '.join(w.text for w in lead)!r}")
                rows.append(_row(line, lead, anchors, columns, " - ".join(c for c in (parent, section) if c), page_no, number, name_amount, anywhere))
    return rows


def parse(pdf: Path, source: dict) -> list[dict]:
    return parse_pages(page_words_fine(pdf, text_flow=source.get("text_flow", False)), source["columns"], source.get("header"),
                       source.get("wrapped_names", False), source.get("titles", ()), source.get("text_values", ()), source.get("furniture", ()), source.get("name_amount", False), source.get("free_sections", False),
                       source.get("invalid_values", ()), source.get("name_below", False))

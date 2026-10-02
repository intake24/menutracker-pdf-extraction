"""Tables whose left columns are labels printed once beside several rows (Domino's pizzas: pizza, cheese, crust, then a size per row).

A data line is a size word followed by a fixed number of figures. Each left column holds labels centred beside the rows they
cover, so every row is given the label whose centre fits best (rows are split into contiguous groups, one per label, by
`allergen_matrix._partition`). Rotated labels (a cheese name printed sideways) are read in bottom-to-top order.

Source options (config/chains.yaml):
  pages      pages to read (numbers and "a-b" ranges)
  columns    the dictionary column of each figure, left to right (every data line must have exactly this many)
  left       label columns, left to right: {column: <dictionary column>, x0: <left edge in pt>, x1: <right edge, default the next column's x0>, rotated: <bool>}; the first
             is the product name; words left of `size_x0` belong to the column whose x0 is the largest not above them
  size_order the sizes from largest to smallest; a row whose size is not smaller than the one above starts a new lowest-level group
  starts_at  (on a label column) {lower column: value}: a new group of this label starts at every group of the lower label with that value
  header_word  a word that appears in every column-title block (default Energy); words level with it are not labels
  shared_row, shared_columns  a size label ("per 100g") whose row is not a row of its own: its figures, named by shared_columns,
             are copied onto the rows that follow it until the next such row
  size_x0    words from here to the first figure are the row's own label (the size), written to `size_column` (default Size)
Anything that doesn't fit (a data line with another number of figures, more labels than rows) raises.
"""
import re
from pathlib import Path

from pipeline.ingest import Word, page_words, page_words_fine
from pipeline.parsers.allergen_matrix import _partition
from pipeline.parsers.numeric_table import NUMBER, _lines

LINE_GAP = 1.7   # label lines within this many line heights are one label


def expand_pages(spec: list) -> list[int]:
    out = []
    for item in spec:
        if isinstance(item, int):
            out.append(item)
        else:
            lo, hi = str(item).split("-")
            out += range(int(lo), int(hi) + 1)
    return out


def _rotated(w: Word) -> bool:
    return len(w.text) > 2 and (w.x1 - w.x0) < 4   # sideways words are only a line height wide


def _clusters(words: list[Word], rotated: bool) -> list[tuple[float, str]]:
    """(centre y, text) of each label in a column."""
    if rotated:   # sideways text: contiguous tall boxes make one label, read from the bottom up
        words = sorted(words, key=lambda w: w.y0)
        groups: list[list[Word]] = []
        for w in words:
            if groups and w.y0 - max(x.y1 for x in groups[-1]) <= 3:
                groups[-1].append(w)
            else:
                groups.append([w])
        return [((min(w.y0 for w in g) + max(w.y1 for w in g)) / 2,
                 " ".join(w.text for w in sorted(g, key=lambda w: -w.y0))) for g in groups]
    out, lines = [], _lines(words)
    group: list[list[Word]] = []
    for line in lines:
        height = line[0].y1 - line[0].y0
        if group and (line[0].y0 + line[0].y1) / 2 - (group[-1][0].y0 + group[-1][0].y1) / 2 <= LINE_GAP * height * 1.2:
            group.append(line)
        else:
            if group:
                out.append(group)
            group = [line]
    if group:
        out.append(group)
    return [(sum((ln[0].y0 + ln[0].y1) / 2 for ln in g) / len(g), " ".join(w.text for ln in g for w in ln)) for g in out]


def _partition_rows(rows: list[float], centres: list[float], breaks: set[int]) -> list[int]:
    """Like allergen_matrix._partition, but a group may not span a row in `breaks` (a row that starts a new group)."""
    n, m = len(rows), len(centres)
    INF = float("inf")
    best = [[INF] * (n + 1) for _ in range(m + 1)]
    cut = [[0] * (n + 1) for _ in range(m + 1)]
    best[0][0] = 0.0
    for k in range(1, m + 1):
        for i in range(k, n + 1):
            for j in range(k - 1, i):
                if any(b in breaks for b in range(j + 1, i)) or best[k - 1][j] == INF:
                    continue
                cost = best[k - 1][j] + abs(sum(rows[j:i]) / (i - j) - centres[k - 1])
                if cost < best[k][i]:
                    best[k][i], cut[k][i] = cost, j
    if best[m][n] == INF:
        raise ValueError(f"{m} labels cannot be fitted to {n} rows with the size order's breaks")
    groups, i = [0] * n, n
    for k in range(m, 0, -1):
        j = cut[k][i]
        groups[j:i] = [k - 1] * (i - j)
        i = j
    return groups


def parse(pdf: Path, source: dict) -> list[dict]:
    columns, left = source["columns"], source["left"]
    size_x0, size_column = source["size_x0"], source.get("size_column", "Size")
    figures = page_words_fine(pdf, text_flow=True)   # rotated labels would otherwise split the words around them
    labels = page_words(pdf)
    rows: list[dict] = []
    for page_no in expand_pages(source["pages"]):
        data = []   # (y, size, numbers)
        for line in _lines(figures[page_no - 1]):
            nums = [w for w in line if NUMBER.match(w.text)]
            if len(nums) < 9:
                continue
            first = nums[0]
            vocab = {part for name in source["size_order"] for part in name.split()}
            size_words = [w.text for w in line if size_x0 <= w.x0 < first.x0 and w.text in vocab]   # not stray letters of a label
            if len(nums) != len(columns):
                raise ValueError(f"page {page_no}: a data line has {len(nums)} figures, config names {len(columns)}: "
                                 f"{' '.join(w.text for w in line)!r}")
            data.append(((line[0].y0 + line[0].y1) / 2, " ".join(size_words), [w.text for w in nums]))
        if not data:
            continue
        top = min(d[0] for d in data) - 40   # labels above the first row (the table's header) are not labels
        # The header block is repeated down the page: words level with a header word ("Energy") are column titles.
        header_ys = sorted({w.y0 for w in labels[page_no - 1] if w.text == source.get("header_word", "Energy")})
        titles = lambda w: any(h - 6 <= w.y0 <= h + 12 for h in header_ys)
        for col in left:
            col["_x1"] = col.get("x1") or next((c["x0"] for c in left if c["x0"] > col["x0"]), size_x0)
        order = {name: i for i, name in enumerate(source["size_order"])}
        ranks = [order.get(d[1], -1) for d in data]
        if -1 in ranks:
            raise ValueError(f"page {page_no}: a size not in size_order: {[d[1] for d in data if d[1] not in order][:3]}")
        breaks = {i for i in range(1, len(data)) if ranks[i] <= ranks[i - 1]}   # the sizes start over: a new crust group
        assigned: list[list[str]] = [[] for _ in data]
        unit_of = list(range(len(data)))   # the group (lowest level) of each row; higher labels cover whole groups
        ys = [d[0] for d in data]
        for level in range(len(left) - 1, -1, -1):
            col = left[level]
            words = [w for w in labels[page_no - 1] if w.y0 >= top and w.y0 <= max(d[0] for d in data) + 6 and not titles(w) and col["x0"] - 2 <= w.x0 < col["_x1"]
                     and bool(col.get("rotated")) == _rotated(w) and not NUMBER.match(w.text)
                     and w.y0 > min(d[0] for d in data) - 6 - (w.y1 - w.y0 if col.get("rotated") else 0)]
            clusters = _clusters(words, bool(col.get("rotated")))
            if not clusters:
                raise ValueError(f"page {page_no}: no labels found for {col['column']!r}")
            starts = col.get("starts_at")
            if level == len(left) - 1:
                groups = _partition_rows(ys, [c[0] for c in clusters], breaks)
            elif starts:   # a new group of this label starts wherever a lower label has the named value
                (low, value), = starts.items()   # `low` is the column directly below this one
                if left[level + 1]["column"] != low:
                    raise ValueError(f"starts_at names {low!r}, which is not the column directly below {col['column']!r}")
                groups, current = [], -1
                for r, u in enumerate(unit_of):
                    new_unit = r == 0 or u != unit_of[r - 1]
                    if new_unit and assigned[r][0] == value:
                        current += 1
                    groups.append(max(current, 0))
                if current + 1 != len(clusters):
                    raise ValueError(f"page {page_no}: {len(clusters)} {col['column']!r} labels but {current + 1} groups start at {value!r}")
            else:   # a higher label covers whole lower groups
                units: dict[int, list[float]] = {}
                for r, u in enumerate(unit_of):
                    units.setdefault(u, []).append(ys[r])
                order_u = sorted(units)
                by_unit = _partition([sum(units[u]) / len(units[u]) for u in order_u], [c[0] for c in clusters])
                groups = [by_unit[order_u.index(u)] for u in unit_of]
            for i, g in enumerate(groups):
                assigned[i].insert(0, clusters[g][1])
            unit_of = groups
        shared: dict[str, str] = {}   # figures of the group's "per 100g" row, repeated on each of its other rows
        for (y, size, nums), labs in zip(data, assigned):
            if size == source.get("shared_row"):
                shared = dict(zip(source["shared_columns"], nums))
                continue
            row = {left[i]["column"]: labs[i] for i in range(len(left))} | {size_column: size, "source_page": page_no}
            row |= shared | dict(zip(columns, nums))
            rows.append(row)
    return rows

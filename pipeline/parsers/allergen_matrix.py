"""Allergen matrix: one row per item (or per size of an item), a mark in the cell under each allergen it holds.

Used for tables whose header carries one (often rotated) label per allergen, e.g. Cineworld:

    Pepsi | Large   | 910 ml | 382.2 |  .  .  .  ✓  .  ▲ ...

Columns come from the x position of the header labels, so a mark is matched to its allergen by position, never by
counting. Several labels can share one dictionary column (each tree nut maps to `treeNuts`; `treeNutSource` then names
the nuts that were marked). The key's marks map through `markers`; an unmarked cell takes `markers[""]`.

Source options (config/chains.yaml):
  labels        header label word -> dictionary allergen column (required; an unknown label in the header raises)
  header_words  other words allowed in the header's allergen area (group titles such as "Allergens", "Tree Nuts")
  markers       mark -> "Yes" / "May contain" / "No", and "" -> what an unmarked cell means
  sizes         words printed in the size column ("Large", "Regular")
  units         units that follow a portion amount ("g", "ml")
  variants      words printed in the size column that name a variant ("Hazelnut"); a size only beside size rows
  note_labels   labels of rows that hold only a note, e.g. "Pick and Mix"; skipped
  group_column_end   x (pt) where the left-most column, holding group names and sub-sections, ends

Left of the allergen area a data line is `[name] [size] <amount> <unit> <kcal>`. An item name is printed once, vertically
centred beside its size rows, so size rows are grouped under the names by distance. Anything the parser can't place
raises instead of being guessed at.
"""
import re
from pathlib import Path

from pipeline.allergens import ALLERGENS, UnknownAllergen
from pipeline.ingest import Word, page_words

NUMBER = re.compile(r"^\d+(?:\.\d+)?$")
LINE_GAP = 3
LABEL_SLACK = 2        # a mark's centre must lie within its label's x-span, +/- this
AREA_SLACK = 4         # the allergen area starts this far left of the first label
NAME_LINE_GAP = 1.7    # lines of one wrapped name are within this many line heights of each other
SIZE_ROW_GAP = 20      # size rows are this close or closer (pt)
MARK_GAP = 12          # marks on a line of their own cover the data rows above and below within this distance
HEADER_TITLES = 45     # group titles ("Allergens", "Tree Nuts") sit this far above the top of the labels
GLUTEN = ["wheat", "rye", "barley", "oats", "spelt", "kamut"]
RANK = {"": 0, "No": 0, "May contain": 1, "Yes": 2}


def _lines(words: list[Word]) -> list[list[Word]]:
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (w.y0 + w.y1) / 2):
        centre = (w.y0 + w.y1) / 2
        if lines and centre - (lines[-1][0].y0 + lines[-1][0].y1) / 2 <= LINE_GAP:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w.x0) for line in lines]


def _centre(w: Word) -> float:
    return (w.y0 + w.y1) / 2


def _cells(right: list[Word], columns: dict[str, Word], markers: dict[str, str], page_no: int,
           texts: list[str]) -> dict[str, str]:
    cells: dict[str, str] = {}
    for w in right:
        if w.text not in markers:
            raise UnknownAllergen(f"page {page_no}, {' '.join(texts)!r}: unknown marker {w.text!r}")
        centre = (w.x0 + w.x1) / 2
        hit = [l for l, lw in columns.items() if lw.x0 - LABEL_SLACK <= centre <= lw.x1 + LABEL_SLACK]
        if len(hit) != 1:
            raise ValueError(f"page {page_no}: {w.text!r} at x={w.x0:.0f} is under no allergen column")
        if hit[0] in cells:
            raise ValueError(f"page {page_no}: two marks under {hit[0]!r} in {' '.join(texts)!r}")
        cells[hit[0]] = markers[w.text]
    return cells


def _caps(w: Word) -> bool:
    """All capitals; a token with no letters ("&") goes along with its neighbours."""
    return all(c.isupper() for c in w.text if c.isalpha())


def _heading(line: list[Word], group_column_end: float) -> str | None:
    """Section heading: a layer of the line that is all capitals, or capitals followed by a "- note" or "*note". A page
    template leaves an older heading printed in white under the current one; they differ by under a point vertically,
    so the line is split into those layers and the lowest one (the visible one) wins."""
    layers: list[list[Word]] = []
    for w in sorted(line, key=lambda w: w.y0):
        if layers and w.y0 - layers[-1][0].y0 <= 0.4:
            layers[-1].append(w)
        else:
            layers.append([w])
    found, notes = [], 0
    for layer in layers:
        layer.sort(key=lambda w: w.x0)
        if layer[0].text.startswith(("-", "*")) and found:
            notes += 1   # the note printed after a heading ("*All weights are approximate")
            continue
        run = []
        for w in layer:
            if not _caps(w):
                break
            run.append(w.text)
        rest = layer[len(run):]
        if any(c.isalpha() for t in run for c in t) and (not rest or rest[0].text.startswith(("-", "*"))) and layer[len(run) - 1].x1 > group_column_end:   # "ICEE" is a name
            found.append(" ".join(run))
    if len(found) + notes != len(layers):
        return None
    return found[-1]


def _partition(rows: list[float], names: list[float]) -> list[int]:
    """Split `rows` (y centres, top to bottom) into len(names) consecutive non-empty groups so that each group's mean y
    is as close as possible to its name's centre. Returns the group index of every row."""
    n, m = len(rows), len(names)
    if m > n:
        raise ValueError(f"{m} names but only {n} size rows")
    INF = float("inf")
    # best[k][i]: least cost of giving the first i rows to the first k names; cut[k][i]: where group k starts
    best = [[INF] * (n + 1) for _ in range(m + 1)]
    cut = [[0] * (n + 1) for _ in range(m + 1)]
    best[0][0] = 0.0
    for k in range(1, m + 1):
        for i in range(k, n + 1):
            for j in range(k - 1, i):
                if best[k - 1][j] < INF:
                    cost = best[k - 1][j] + abs(sum(rows[j:i]) / (i - j) - names[k - 1])
                    if cost < best[k][i]:
                        best[k][i], cut[k][i] = cost, j
    groups, i = [0] * n, n
    for k in range(m, 0, -1):
        j = cut[k][i]
        groups[j:i] = [k - 1] * (i - j)
        i = j
    return groups


def _clusters(frags: list[tuple[float, list[Word]]]) -> list[list[tuple[float, list[Word]]]]:
    """Lines of one wrapped name are within NAME_LINE_GAP line heights of each other."""
    out: list[list[tuple[float, list[Word]]]] = []
    for f in sorted(frags, key=lambda f: f[0]):
        height = f[1][0].y1 - f[1][0].y0
        if out and f[0] - out[-1][-1][0] <= NAME_LINE_GAP * height:
            out[-1].append(f)
        else:
            out.append([f])
    return out


def _assign(rows: list[dict], clusters: list, key: str, page_no: int) -> None:
    """Give every row in `rows` the text of the cluster whose centre its y fits best (see _partition)."""
    groups = _partition([d["y"] for d in rows], [sum(y for y, _ in c) / len(c) for c in clusters])
    for d, g in zip(rows, groups):
        d[key] = " ".join(w.text for _, ws in clusters[g] for w in ws)
        d["group"] = g


def parse_pages(pages: list[list[Word]], labels: dict[str, str], markers: dict[str, str], sizes: list[str],
                units: list[str], group_column_end: float, header_words: list[str] = (), note_labels: list[str] = (), variants: list[str] = ()) -> list[dict]:
    rows: list[dict] = []
    category = ""
    for page_no, words in enumerate(pages, start=1):
        # The header labels are the label words that share one bottom edge; the same words in prose don't.
        by_bottom: dict[int, list[Word]] = {}
        for w in words:
            if w.text in labels:
                by_bottom.setdefault(round(w.y1), []).append(w)
        found = max(by_bottom.values(), key=len, default=[])
        if len(found) < len(labels) / 2:
            continue   # intro and key pages
        if len({w.text for w in found}) != len(found):
            raise ValueError(f"page {page_no}: an allergen column label appears twice in the header")
        bottom = max(w.y1 for w in found)
        area = min(w.x0 for w in found) - AREA_SLACK
        top = min(w.y0 for w in found) - HEADER_TITLES
        for w in words:
            if top <= w.y0 and w.y1 <= bottom and w.x0 >= area and w.text not in labels and w.text not in header_words:
                raise ValueError(f"page {page_no}: unknown header word {w.text!r} in the allergen area")
        columns = {w.text: w for w in found}

        data: list[dict] = []
        fragments: list[tuple[float, list[Word]]] = []      # group-column text without a data row
        markline: list[tuple[float, dict[str, str], list[str]]] = []   # marks on a line with no data: they apply to a size group
        for line in _lines([w for w in words if w.y0 > bottom]):
            left = [w for w in line if w.x0 < area]
            right = [w for w in line if w.x0 >= area]
            texts = [w.text for w in left]
            if not any(NUMBER.match(t) for t in texts):
                if heading := _heading(line, group_column_end):
                    category = heading
                    continue
                if right and any(w.text not in markers for w in right):
                    if any(w.text in markers for w in right):
                        raise ValueError(f"page {page_no}: marks on a note line: {' '.join(w.text for w in line)!r}")
                    continue   # a note spanning the allergen columns ("Allergen information is on the display")
                item_col = [w for w in left if w.x1 > group_column_end]
                if " ".join(texts) in note_labels:
                    continue   # label of a row that holds only a note ("Pick and Mix")
                if item_col:   # an item with no amount or calories printed (draught beer)
                    group = [w for w in left if w.x1 <= group_column_end]
                    if group:
                        fragments.append((_centre(line[0]), group))
                    data.append({"y": _centre(line[0]), "kcal": "", "per100": False, "amount": "", "unit": "",
                                 "middle": " ".join(w.text for w in item_col), "listed": False,
                                 "cells": _cells(right, columns, markers, page_no, texts), "category": category})
                    continue
                if left:
                    fragments.append((_centre(line[0]), left))
                if right:
                    markline.append((_centre(line[0]), _cells(right, columns, markers, page_no, texts), texts))
                continue
            # [group name] [size | item name] (<amount> <unit> | Per 100g) [<kcal>]
            per100 = texts[-3:-1] == ["Per", "100g"] and NUMBER.match(texts[-1]) is not None
            if per100 or (texts[-2] in units and NUMBER.match(texts[-3]) and NUMBER.match(texts[-1])):
                tail, kcal = 3, texts[-1]
            elif texts[-1] in units and NUMBER.match(texts[-2]):
                tail, kcal = 2, ""          # alcohol: an amount and no calories printed
            else:
                raise ValueError(f"page {page_no}: cannot read a data row: {' '.join(texts)!r}")
            rest = left[:-tail]
            group = [w for w in rest if w.x1 <= group_column_end]
            middle = " ".join(w.text for w in rest if w.x1 > group_column_end)
            if not middle:
                raise ValueError(f"page {page_no}: a data row without a size or an item name: {' '.join(texts)!r}")
            if group:
                fragments.append((_centre(line[0]), group))
            data.append({"y": _centre(line[0]), "kcal": kcal, "per100": per100,
                         "amount": "" if per100 else texts[-tail], "unit": "" if per100 else texts[-tail + 1],
                         "middle": middle, "listed": True,
                         "cells": _cells(right, columns, markers, page_no, texts), "category": category})

        # A size word is a size; variant words ("Hazelnut") are sizes only in a run of two or more, or beside a size row:
        # a lone "Chocolate" can be a sauce. A row printed with no amount is never a size.
        for d in data:
            d["is_size"] = d["listed"] and d["middle"] in sizes
            d["variant"] = False
        i = 0
        while i < len(data):   # a run of consecutive variant rows
            j = i
            while j < len(data) and data[j]["listed"] and data[j]["middle"] in variants and (
                    j == i or abs(data[j]["y"] - data[j - 1]["y"]) <= SIZE_ROW_GAP):
                j += 1
            beside = [k for k in (i - 1, j) if 0 <= k < len(data) and data[k]["is_size"]
                      and abs(data[k]["y"] - data[i if k < i else j - 1]["y"]) <= SIZE_ROW_GAP]
            if j > i and (j - i >= 2 or beside):
                for d in data[i:j]:
                    d["is_size"] = d["variant"] = True
            i = max(j, i + 1)
        for d in data:
            d["size"], d["item"] = (d["middle"], "") if d["is_size"] else ("", d["middle"])
        sized = [d for d in data if d["size"]]
        unsized = [d for d in data if not d["size"]]
        # A group-column cluster beside size rows is the item name; beside item rows it is a sub-section.
        sized_ys = [d["y"] for d in sized]
        names, subs = [], []
        for c in _clusters(fragments):
            y = sum(f[0] for f in c) / len(c)
            nearest = min(data, key=lambda d: abs(d["y"] - y), default=None)
            (names if nearest is not None and nearest["size"] else subs).append(c)
        # Marks printed beside a size group's rows (on a data row's line or between lines) cover the whole group; marks
        # on a line of their own beside single items belong to the item on that line.
        if sized:
            if not names:
                raise ValueError(f"page {page_no}: size rows without any item name")
            _assign(sized, names, "item", page_no)
        elif names:
            raise ValueError(f"page {page_no}: item names without size rows")
        for y, cells, texts in markline:
            above = max((d for d in data if d["y"] <= y), key=lambda d: d["y"], default=None)
            below = min((d for d in data if d["y"] > y), key=lambda d: d["y"], default=None)
            near = [d for d in (above, below) if d is not None and abs(d["y"] - y) <= MARK_GAP]
            if not near:
                raise ValueError(f"page {page_no}: marks beside {texts} at y={y:.0f} are not beside any row")
            for d in near:   # a cell merged across two rows leaves its marks between them
                d["cells"] = d["cells"] | cells
        for g in {d["group"] for d in sized}:
            members = [d for d in sized if d["group"] == g and not d["variant"]]   # variants carry their own marks
            merged: dict[str, str] = {}
            for d in members:
                for label, value in d["cells"].items():
                    if RANK[value] >= RANK[merged.get(label, "")]:
                        merged[label] = value
            for d in members:
                d["cells"] = merged
        if subs and unsized:
            for cat in {d["category"] for d in unsized}:   # a sub-section never runs past its heading
                rows_here = [d for d in unsized if d["category"] == cat]
                here = [c for c in subs if min(unsized, key=lambda d: abs(d["y"] - sum(f[0] for f in c) / len(c)))["category"] == cat]
                if here:
                    _assign(rows_here, here, "sub", page_no)
            for d in (d for d in unsized if "sub" in d):
                d["category"] = f"{d['category']} - {d['sub']}" if d["category"] else d["sub"]

        used = {labels[l] for l in columns}
        for d in data:
            basis = "Per 100g/ml" if d["per100"] else "Per Portion"
            row = {"Product_Name": d["item"], "Category": d["category"], "source_page": page_no}
            if d["kcal"]:
                row[f"energykCal_{basis}"] = d["kcal"]
            if not d["per100"]:
                row |= {"Serving_Size": d["amount"], "Serving_Size_Unit": d["unit"]}
            if d["size"]:
                row["Size"] = d["size"]
            best: dict[str, str] = {}
            nuts: list[str] = []
            for label, value in d["cells"].items():
                col = labels[label]
                if RANK[value] >= RANK[best.get(col, "")]:
                    best[col] = value
                if col == "treeNuts" and value:
                    nuts.append(f"{label} ({value})")
            row |= {a: best.get(a, markers[""]) if a in used else "" for a in ALLERGENS}
            grains = [row[c] for c in GLUTEN]
            row["gluten"] = "Yes" if "Yes" in grains else ("May contain" if "May contain" in grains else "")
            if nuts:
                row["treeNutSource"] = ", ".join(nuts)
            rows.append(row)
    return rows


def parse(pdf: Path, source: dict) -> list[dict]:
    return parse_pages(page_words(pdf), source["labels"], source["markers"], source["sizes"], source["units"],
                       source["group_column_end"], source.get("header_words", []), source.get("note_labels", []), source.get("variants", []))

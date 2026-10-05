"""Drink tables: product name and allergens printed once beside a product's size rows, then 9 figures per group (Coffee #1 beverages).

A page holds several tables. Each has a bold capital title (and a subtitle), a line of group labels ("Per 100ml", "Per product"), a header
line (PRODUCT, ALLERGENS and, usually, SIZE) and data rows: a size word (if the table has a SIZE column) and the figures. The column
titles above the figures are rotated and cannot be read, so the figure order is fixed by `nutrients` and checked by the arithmetic flags.
A thin black rule is printed under every product: the space between two rules is one product, holding its name (one or more lines,
left of the allergen column), its allergen text and one data row per size. Allergen text ("MILK, OAT") goes through the allergen reader.

Source options (config/chains.yaml):
  nutrients  the nine figures of a group, left to right, as dictionary nutrient names
  groups     printed group label -> {base: dictionary base, serving: "15 ml" (optional), split: true (optional)}; groups that share a base are
             split into rows of their own (the serving size then comes from the label), the others are columns of one row
  sizes      words printed in the size column ("Regular", "12oz")
  extra_headers  headers printed with the group labels that are not figure groups ("Vitamin Content")
  figure_titles  the nine figure titles in the printed order (KJ, Kcal, ...); they are rotated, so they are read letter by letter and
             a table whose titles differ stops the run
  allergen_text  printed allergen word -> the text given to the allergen reader ("OAT": "Oats (Gluten Free)": the guide says its oat milk is made
             with gluten free oats and lists OAT because of avenin, so gluten is not set)
  furniture  texts printed at the top of every page
  markers    {"": "No"}: the guide lists every allergen of a drink, so an unlisted one is absent
A group label that is not in `groups`, a table whose figure columns do not number nine per group, a product with no name, or text
between two rules that is not part of a product raises.
"""
import re
from pathlib import Path

import pdfplumber

from pipeline.allergens import parse_allergens

LINE_GAP = 3
NAME_LINE_GAP = 1.7   # lines of one wrapped name are within this many line heights of each other
COLUMN_GAP = 6        # right edges further apart than this (pt) are different figure columns
TITLE_RATIO = 1.05   # bold type this much larger than the body text is a title
MIN_SIZE = 6          # the rotated column titles come out as tiny letters: ignore them
NUMBER = re.compile(r"^<?\d+(\.\d+)?$")


def _centre(w: dict) -> float:
    return (w["top"] + w["bottom"]) / 2


def _lines(words: list[dict]) -> list[list[dict]]:
    out: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (_centre(w), w["x0"])):
        if out and _centre(w) - _centre(out[-1][0]) <= LINE_GAP:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in out]


def _text(line: list[dict]) -> str:
    return " ".join(w["text"] for w in line)


def _clusters(lines: list[list[dict]]) -> list[list[list[dict]]]:
    out: list[list[list[dict]]] = []
    for line in lines:
        height = line[0]["bottom"] - line[0]["top"]
        if out and _centre(line[0]) - _centre(out[-1][-1][0]) <= NAME_LINE_GAP * height:
            out[-1].append(line)
        else:
            out.append([line])
    return out


def _anchors(edges: list[float]) -> list[float]:
    edges = sorted(edges)
    groups = [[edges[0]]]
    for x in edges[1:]:
        if x - groups[-1][-1] > COLUMN_GAP:
            groups.append([])
        groups[-1].append(x)
    return [sum(g) / len(g) for g in groups]


def _is_title(line: list[dict], body: float) -> bool:
    """A table's title: bold type larger than the page's body text (the pages are scaled differently, so the size is relative)."""
    return "Bold" in line[0]["fontname"] and line[0]["size"] >= TITLE_RATIO * body and not _text(line).startswith("Per ") and line[0]["text"] != "PRODUCT"


def parse_page(words: list[dict], rules: list[float], source: dict, page_no: int, titles_chars: list[dict] | None = None) -> list[dict]:
    furniture = tuple(source.get("furniture", ()))
    words = [w for w in words if w["size"] >= MIN_SIZE]
    lines = [line for line in _lines(words) if not _text(line).startswith(furniture)]
    heads = [i for i, line in enumerate(lines) if _text(line).startswith("Per ") and "Bold" in line[0]["fontname"]]   # the group labels start a table
    sizes = [round(w["size"], 1) for w in words if "Bold" not in w["fontname"]]
    body_size = max(set(sizes), key=sizes.count) if sizes else 9.5
    if not heads:
        if any(sum(bool(NUMBER.match(w["text"])) for w in line) >= 9 for line in lines):
            raise ValueError(f"page {page_no}: figures but no table header (group labels) found")
        return []
    starts = []   # a table starts at its title; a table with none (a second table under one title) starts at its group labels
    for k, h in enumerate(heads):
        floor = heads[k - 1] if k else -1
        titles = [i for i in range(floor + 1, h) if _is_title(lines[i], body_size)]
        if not titles and k == 0:
            raise ValueError(f"page {page_no}: a table with group labels but no title above them")
        starts.append(titles[0] if titles else h)
    out, title_lines = [], []
    for k, h in enumerate(heads):
        end = starts[k + 1] if k + 1 < len(heads) else len(lines)
        if starts[k] < h:
            title_lines = lines[starts[k]:h]
        top, bottom = _centre(lines[h][0]), (_centre(lines[end][0]) if end < len(lines) else 1e9)
        header_words = {"PRODUCT", "ALLERGENS", "SIZE", *source.get("extra_headers", ()), *(x for h in source.get("extra_headers", ()) for x in h.split())}
        dropped = [l for l in lines[h + 1:end] if any(w["text"] in ("PRODUCT", "ALLERGENS", "SIZE") for w in l) or all(w["text"] in header_words for w in l)]
        if any(sum(bool(NUMBER.match(w["text"])) for w in l) >= 9 for l in dropped):
            raise ValueError(f"page {page_no}: a line with figures also holds a header word, so it would be dropped: {_text(dropped[0])[:50]!r}")
        body = [l for l in lines[h + 1:end] if l not in dropped]
        out += _table(title_lines + [lines[h]], body, [r for r in rules if top < r < bottom], source, page_no, titles_chars)
    return out


SIZE_AMOUNT = re.compile(r"^(\d+(?:\.\d+)?)\s?(oz|ml|g)$")
VITAMIN = re.compile(r"^(\d+(?:\.\d+)?)(mg|ug)$")


def _table(above: list[list[dict]], body: list[list[dict]], rules: list[float], source: dict, page_no: int, titles_chars: list[dict] | None = None) -> list[dict]:
    nutrients, groups, sizes = source["nutrients"], source["groups"], set(source.get("sizes", ()))
    labels = above[-1]
    titles = above[:-1]
    title = _text(titles[0])
    subtitle = " ".join(_text(l) for l in titles[1:])
    runs: list[list[dict]] = [[labels[0]]]
    for w in labels[1:]:   # "Per 100ml" is two words: a gap of 12 pt or more starts the next label
        if w["x0"] - runs[-1][-1]["x1"] < 12:
            runs[-1].append(w)
        else:
            runs.append([w])
    group_names = [" ".join(w["text"] for w in r) for r in runs]
    extra_headers = set(source.get("extra_headers", ()))
    group_names = [g for g in group_names if g not in extra_headers]   # e.g. "Vitamin Content", the header of a column of mg/ug values
    for label in group_names:
        if label not in groups:
            raise ValueError(f"page {page_no}: the group label {label!r} is not in `groups`")
    need = len(group_names) * len(nutrients)
    rows, name_words, allergen_words, extras, size_found = [], [], [], [], False
    for line in body:
        numbers = [w for w in line if NUMBER.match(w["text"])]
        figures = numbers[-need:] if len(numbers) >= need else []
        rest = [w for w in line if not any(w is f for f in figures)]
        if figures:
            row = {"y": _centre(line[0]), "figures": figures, "size": ""}
            rows.append(row)
        for w in rest:
            if w["text"] in sizes and "Bold" not in w["fontname"]:   # names are bold ("Mini Marshmallows"), sizes are not
                size_found = True
                if not figures:
                    raise ValueError(f"page {page_no}, {title}: the size {w['text']!r} is on a line with no figures")
                row["size"] = (row["size"] + " " + w["text"]).strip()
            elif VITAMIN.match(w["text"]):
                extras.append(w)
            elif "Bold" not in w["fontname"] and w["text"].replace(",", "").isupper():
                allergen_words.append(w)
            else:
                name_words.append(w)
    if not rows:
        raise ValueError(f"page {page_no}, {title}: the table has no data rows")
    if titles_chars is not None and source.get("figure_titles"):
        read = _figure_titles(titles_chars, _centre(labels[0]), min(r["y"] for r in rows))
        if read != list(source["figure_titles"]) * len(group_names):
            raise ValueError(f"page {page_no}, {title}: the figure titles read {read}, the config expects {list(source['figure_titles']) * len(group_names)}")
    anchors = _anchors([w["x1"] for r in rows for w in r["figures"]])
    if len(anchors) != need:
        raise ValueError(f"page {page_no}, {title}: found {len(anchors)} figure columns, expected {need}")

    def inside(lo: float, hi: float, ws: list[dict]) -> list[dict]:
        return [w for w in ws if lo < _centre(w) < hi]
    bounds = [-1e9] + [r for r in rules] + [1e9]
    spans = [(lo, hi) for lo, hi in zip(bounds, bounds[1:]) if any(lo < r["y"] < hi for r in rows)]
    products = []
    if len(spans) >= 2 and sum(1 for lo, hi in spans for _ in [0] if inside(lo, hi, name_words)) == len(spans):
        for lo, hi in spans:   # a rule under every product: the space between two rules is one product
            if len(_clusters(_lines(inside(lo, hi, name_words)))) > 1:
                raise ValueError(f"page {page_no}, {title}: more than one name between two rules ({_text(inside(lo, hi, name_words)[:3])!r} ...): a rule is missing")
            products.append({"rows": [r for r in rows if lo < r["y"] < hi], "names": inside(lo, hi, name_words), "allergens": inside(lo, hi, allergen_words)})
    elif not size_found:   # no size column: every row is a product, named by the text level with it
        for r in rows:
            products.append({"rows": [r], "names": [w for w in name_words if abs(_centre(w) - r["y"]) <= LINE_GAP * 2],
                             "allergens": [w for w in allergen_words if abs(_centre(w) - r["y"]) <= LINE_GAP * 2]})
    else:   # names are centred beside their size rows: group the rows under the names by distance
        from pipeline.parsers.allergen_matrix import _partition
        clusters = _clusters(_lines(name_words))
        if len(clusters) > len(rows):
            raise ValueError(f"page {page_no}, {title}: {len(clusters)} names but {len(rows)} rows")
        centres = [sum(_centre(l[0]) for l in c) / len(c) for c in clusters]
        group_of = _partition([r["y"] for r in rows], centres)
        products = [{"rows": [r for r, g in zip(rows, group_of) if g == i], "names": [w for l in c for w in l], "allergens": []} for i, c in enumerate(clusters)]
        for w in allergen_words:
            min(products, key=lambda p: abs(sum(r["y"] for r in p["rows"]) / len(p["rows"]) - _centre(w)))["allergens"].append(w)
    claimed = {id(w) for p in products for w in p["names"] + p["allergens"]}
    left = [w for w in name_words + allergen_words if id(w) not in claimed]
    if left:
        raise ValueError(f"page {page_no}, {title}: text that belongs to no product: {_text(sorted(left, key=lambda w: (w['top'], w['x0'])))[:60]!r}")
    for w in extras:
        if not any(abs(_centre(w) - r["y"]) <= LINE_GAP * 2 for r in rows):
            raise ValueError(f"page {page_no}, {title}: the vitamin content {w['text']!r} is by no row")
    out = []
    split = [g for g in group_names if groups[g].get("split")]
    for p in products:
        if not p["names"]:
            raise ValueError(f"page {page_no}, {title}: a product with no name at y={p['rows'][0]['y']:.0f}")
        name = " ".join(_text(l) for l in _lines(p["names"]))
        text = " ".join(_text(l) for l in _lines(p["allergens"]))
        for printed, meaning in source.get("allergen_text", {}).items():   # e.g. OAT -> "Oats (Gluten Free)"
            text = re.sub(rf"\b{re.escape(printed)}\b", meaning, text)
        allergens = parse_allergens(text, "", source.get("markers", {}).get("", ""))
        for r in p["rows"]:
            cells: dict[int, str] = {}
            for w in r["figures"]:
                i = min(range(len(anchors)), key=lambda j: abs(anchors[j] - w["x1"]))
                if abs(anchors[i] - w["x1"]) > COLUMN_GAP or i in cells:
                    raise ValueError(f"page {page_no}, {title}, {name}: a figure {w['text']!r} is under no column, or two are in one")
                cells[i] = w["text"]
            base = {"Product_Name": name, "Category": title, "source_page": page_no} | ({"Product_Description": subtitle} if subtitle else {}) \
                | ({"Size": r["size"]} if r["size"] else {}) | allergens
            if (m := SIZE_AMOUNT.match(r["size"])) and not split:   # a size like "12oz" is also the serving size
                base |= {"Serving_Size": m.group(1), "Serving_Size_Unit": m.group(2)}
            for w in extras:   # the vitamin content printed beside a row: mg is vitamin C, ug is vitamin B12 (the names say so)
                if abs(_centre(w) - r["y"]) <= LINE_GAP * 2:
                    amount, unit = VITAMIN.match(w["text"]).groups()
                    column = {"mg": "vitaminC", "ug": "vitaminB12"}[unit]
                    if {"vitaminC": "vitamin c", "vitaminB12": "b12"}[column] not in name.lower():
                        raise ValueError(f"page {page_no}, {name}: the vitamin content {w['text']!r} does not match the name")
                    base[f"{column}_Per Portion"] = amount
            for gi, label in enumerate(group_names):
                spec = groups[label]
                values = {f"{n}_{spec['base']}": cells[gi * len(nutrients) + ni] for ni, n in enumerate(nutrients)}
                if split:   # groups that share a base are rows of their own: the serving size comes from the label
                    amount, unit = spec["serving"].split()
                    out.append(base | values | {"Serving_Size": amount, "Serving_Size_Unit": unit})
                else:
                    base |= values
            if not split:
                out.append(base)
    return out


def _figure_titles(chars: list[dict], y_lo: float, y_hi: float) -> list[str]:
    """The rotated column titles (KJ, Kcal, ...) between the group labels and the first data row, read letter by letter, left to right."""
    columns: dict[int, list[dict]] = {}
    for c in chars:
        if y_lo < (c["top"] + c["bottom"]) / 2 < y_hi:
            columns.setdefault(round((c["x0"] + c["x1"]) / 2 / 6), []).append(c)
    return ["".join(c["text"] for c in sorted(cs, key=lambda c: -c["top"])) for _, cs in sorted(columns.items())]


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
            page = doc.pages[n - 1]
            words = page.extract_words(extra_attrs=["fontname", "size"], x_tolerance=1.5, y_tolerance=1)
            rules = sorted((r["top"] + r["bottom"]) / 2 for r in page.rects if r["bottom"] - r["top"] <= 1.5 and r["x1"] - r["x0"] >= 300)
            small = [c for c in page.chars if c["size"] < MIN_SIZE]   # the rotated figure titles are tiny letters
            rows += parse_page(words, rules, source, n, small)
    return rows

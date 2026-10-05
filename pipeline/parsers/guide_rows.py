"""Guide rows: name on the left, ingredient declaration in the middle, figures, and a summary column of allergens on the right (Starbucks).

Rows are the spaces between the horizontal rules that are wider than a column of text and narrower than the page (page borders are as wide
as the page). A row with figures is a product (a drink has one figure line per size, a food one); a row with only large type is a section
bar ("Loaf Cakes & Muffins", with "per portion" in dashes); anything else raises. The summary column of allergens is the source of the
allergen cells; the bold capital words of the declaration are read as well and any difference is flagged (two readings of one statement).

Source options (config/chains.yaml):
  name_x1          right edge (pt) of the name column; bold words left of it are the name
  figures_x0       left edge of the figure columns; allergens_x0 left edge of the summary column of allergens
  nutrients        the figures of a line, left to right, as dictionary nutrient names; or {number of figure columns: names} when pages differ
  diet_columns     dictionary columns for the Y/N cells between the name and the ingredients, left to right (food only)
  size_x0          left edge of the size column of a drink ("Tall", "Grande", "Venti", "Single", "Doppio"); words there on a figure line are the size
  heading_size     smallest type size (pt) of a section bar's text
  default_base     the base of figures under a bar with no label ("Per Portion"); no_allergen_marks: marks in the summary column that mean none ("-")
  bar_bases        text of the bar's dashed label ("per portion") -> dictionary base ("Per Portion"); an unknown label raises
  menu_word        the page's menu is the last "|"-separated part of the running head
  furniture        texts of the page head; markers {"": "No"}: the guide summarises every allergen, so an unlisted one is absent
A row with no name, a figure line with a wrong number of figures, a Y/N cell that is not Y or N, text that is not a name, a declaration,
a figure, an allergen, a size or a bar raises.
"""
import re
from pathlib import Path

import pdfplumber

from pipeline.allergens import parse_allergens
from pipeline.parsers import product_blocks as pb

LINE_GAP = 3
COLUMN_GAP = 6
NUMBER = re.compile(r"^<?\d+(\.\d+)?(?:g|mg)?$")   # a figure, as printed ("<0.5g" has its unit)


def _centre(w: dict) -> float:
    return (w["top"] + w["bottom"]) / 2


def _lines(words: list[dict]) -> list[list[dict]]:
    return pb._lines(words)


def _text(words: list[dict]) -> str:
    return " ".join(w["text"] for line in _lines(words) for w in line)


def _anchors(edges: list[float]) -> list[float]:
    edges = sorted(edges)
    groups = [[edges[0]]]
    for x in edges[1:]:
        if x - groups[-1][-1] > COLUMN_GAP:
            groups.append([])
        groups[-1].append(x)
    return [sum(g) / len(g) for g in groups]


def parse_page(words: list[dict], rules: list[tuple[float, float, float]], source: dict, page_no: int) -> list[dict]:
    """`rules`: (y, x0, x1) of the page's horizontal rules."""
    name_x1, fig_x0, all_x0 = source["name_x1"], source["figures_x0"], source["allergens_x0"]
    sets = source["nutrients"] if isinstance(source["nutrients"], dict) else {len(source["nutrients"]): source["nutrients"]}
    need = max(sets)
    wide = sorted(y for y, x0, x1 in rules if x1 - x0 >= 300)
    page_w = max(x1 for _, _, x1 in rules) if rules else 0
    border = [y for y, x0, x1 in rules if x1 - x0 >= page_w - 5]   # the rules as wide as the page: the top, and the footer bars
    product_y = min((_centre(w) for w in words if w["text"] == "Product"), default=None)
    if product_y is None:
        raise ValueError(f"page {page_no}: no table header (Product, Ingredients) found")
    below = [y for y in wide if y > product_y]
    if not below:
        raise ValueError(f"page {page_no}: no rule under the table header found")
    body_top = below[0]   # the rule under the header row
    footer = min([y for y in border if y > body_top] or [1e9])
    seps = [y for y in wide if body_top <= y < footer]
    head = _lines([w for w in words if w["top"] < 40])
    menu = re.sub(r"\s*Version:.*$", "", _text([w for l in head for w in l]).split("|")[-1]).strip() if head else ""   # the head ends with the guide's version
    if not menu:
        raise ValueError(f"page {page_no}: no running head found")
    out = []
    # section bars first: lines of large type (a bar's label can be drawn above the rule that bounds the row it belongs to)
    big = [w for w in words if w["size"] >= source.get("heading_size", 6.8) and body_top <= _centre(w) < footer and w["top"] > body_top - 1]
    bars = []   # (y, section, base)
    for line in _lines(big):
        text = _text(line)
        parts = [x.strip() for x in re.sub(r"[-\u2013\u2014]{3,}", "|", text).split("|") if x.strip()]
        bar_bases = source.get("bar_bases", {})
        if len(parts) > 1 and parts[-1].lower() in bar_bases:
            bars.append((_centre(line[0]), parts[0], bar_bases[parts[-1].lower()]))
        elif len(parts) > 1:
            raise ValueError(f"page {page_no}: the bar label {parts[-1]!r} is not in `bar_bases`")
        else:
            bars.append((_centre(line[0]), parts[0] if parts else "", None))
    bar_ids = {id(w) for w in big}
    words = [w for w in words if id(w) not in bar_ids]
    edges = [w["x1"] for w in words if NUMBER.match(w["text"]) and fig_x0 <= w["x0"] < all_x0 and w["size"] >= 5.5 and body_top <= _centre(w) < footer]
    anchors = _anchors(edges) if edges else []
    if anchors and len(anchors) not in sets:
        raise ValueError(f"page {page_no}: found {len(anchors)} figure columns, expected one of {sorted(sets)}")
    nutrients = sets[len(anchors)] if anchors else []
    bounds = sorted(set(seps)) + [footer]   # the last row of a page may have no rule under it: it ends at the footer
    for lo, hi in zip(bounds, bounds[1:]):
        inside = [w for w in words if lo <= _centre(w) < hi and w["size"] >= 5.5]
        if not inside:
            continue
        section, base = next(((s, b) for y, s, b in reversed(bars) if y < min(_centre(w) for w in inside)), ("", None))
        figures_by_line = []
        for line in _lines(inside):
            nums = [w for w in line if NUMBER.match(w["text"]) and fig_x0 <= w["x0"] < all_x0]
            if nums:
                if len(nums) > need:
                    raise ValueError(f"page {page_no}: a line has {len(nums)} figures, at most {need} expected: {_text(line)[:60]!r}")
                figures_by_line.append(nums)
        if figures_by_line:
            for w in inside:
                if fig_x0 <= w["x0"] < all_x0 and not NUMBER.match(w["text"]):
                    raise ValueError(f"page {page_no}: the word {w['text']!r} in the figure columns of a product row is not a figure")
        if not figures_by_line:
            raise ValueError(f"page {page_no}: text in a row with no figures that is not a section bar: {_text(inside)[:60]!r}")
        name_words = [w for w in inside if w["x1"] <= name_x1 and "Bold" in w["fontname"]]
        diet_words = [w for w in inside if w["x1"] <= name_x1 + 60 and "Bold" not in w["fontname"] and w["x0"] < source.get("ingredients_x0", 130)] if source.get("diet_columns") else []
        allergen_words = [w for w in inside if w["x0"] >= all_x0 and not NUMBER.match(w["text"])]
        figure_ids = {id(w) for nums in figures_by_line for w in nums}
        size_x0 = source.get("size_x0")
        size_words = [w for w in inside if size_x0 is not None and size_x0 <= w["x0"] < fig_x0 and not NUMBER.match(w["text"]) and "Bold" not in w["fontname"]]
        declaration = [w for w in inside if id(w) not in figure_ids and w not in name_words and w not in diet_words and w not in allergen_words and w not in size_words]
        stray = [w for w in declaration if w["x0"] < name_x1 or w["x0"] >= all_x0 or "Bold" in w["fontname"] and w["x1"] <= name_x1]
        if stray:
            raise ValueError(f"page {page_no}: text left of the declaration that is not a name: {_text(stray)[:60]!r}")
        if not name_words:
            raise ValueError(f"page {page_no}: a product row at y={lo:.0f} has no name")
        name = _text(name_words)
        base = base or source.get("default_base")
        if base is None:
            raise ValueError(f"page {page_no}, {name}: figures with no 'per portion' bar above them")
        cells = {}
        diet = [w for l in _lines(diet_words) for w in l]
        cols = source.get("diet_columns", [])
        if cols:
            if len(diet) != len(cols):
                raise ValueError(f"page {page_no}, {name}: {len(diet)} Y/N cells, expected {len(cols)}")
            for col, w in zip(cols, diet):
                if w["text"] not in ("Y", "N"):
                    raise ValueError(f"page {page_no}, {name}: the diet cell {w['text']!r} is not Y or N")
                cells[col] = w["text"]
        elif diet:
            raise ValueError(f"page {page_no}, {name}: text where no Y/N column is configured: {_text(diet)!r}")
        # allergens: the summary column, checked against the bold capitals of the declaration
        extras = source.get("allergen_words", {})
        summary = _allergens_text(allergen_words, extras, page_no, name, source.get("no_allergen_marks", ()))
        flags = ""
        read = pb._allergens(declaration, {**source, "may_phrases": ["May contain"]}, page_no, name)
        if read.get("oats") == "Yes" and read.get("gluten") != "Yes":   # the declaration says the oats are gluten free: oats without gluten
            summary = re.sub(r"\bOats\b(?! \()", "Oats (Gluten Free)", summary)
        got = parse_allergens(summary, "", source.get("markers", {}).get("", ""))
        diff = sorted(k for k in got if k != "treeNutSource" and (got[k] == "Yes") != (read.get(k) == "Yes"))
        if diff:
            flags = "warn: the allergen column and the bold capitals of the ingredients differ on " + ", ".join(diff)
        sizes_found = [w for l in _lines(size_words) for w in l]
        lines = sorted(figures_by_line, key=lambda nums: _centre(nums[0]))
        if size_words and len(sizes_found) != len(lines):
            raise ValueError(f"page {page_no}, {name}: {len(sizes_found)} sizes for {len(lines)} figure lines")
        for k, nums in enumerate(lines):
            row = {"Product_Name": name, "Category": " - ".join(x for x in (menu, section) if x), "source_page": page_no} | cells
            if size_words:
                row["Size"] = sizes_found[k]["text"]
            cells_ = {}
            for w in nums:   # a cell the guide leaves blank (a drink with no fibre figure) stays blank: figures go to their column by position
                i = min(range(len(anchors)), key=lambda j: abs(anchors[j] - w["x1"]))
                if abs(anchors[i] - w["x1"]) > COLUMN_GAP or i in cells_:
                    raise ValueError(f"page {page_no}, {name}: a figure {w['text']!r} is under no column, or two are in one")
                cells_[i] = w["text"]
            row |= got | {f"{nutrients[i]}_{base}": v for i, v in cells_.items()}
            if flags:
                row["flags"] = flags
            row["Ingredients"] = _text(declaration)
            out.append(row)
    return out


def _allergens_text(words: list[dict], extras: dict, page_no: int, name: str, source_none: list[str] = ()) -> str:
    terms = []
    table = pb.BASE_WORDS | {k.lower(): v for k, v in extras.items()}
    nothing = set(source_none)
    for w in words:
        token = pb._token(w["text"])
        if token and token not in nothing and not re.fullmatch(r"[-\u2013\u2014]+", token):   # a dash means none
            term = pb._allergen_term(token, table, page_no, name)
            if term:
                terms.append(term)
    return ", ".join(dict.fromkeys(terms))


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
            rules = [(round(e["top"]), e["x0"], e["x1"]) for e in page.edges if e["orientation"] == "h"]
            rows += parse_page(words, rules, source, n)
    return rows

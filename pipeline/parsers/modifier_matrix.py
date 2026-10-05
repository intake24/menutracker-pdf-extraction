"""Modifier matrix: a name, a line per way it is served, its calories and a tick under each allergen it holds (Starbucks Modifiers pages).

The column labels are rotated (read letter by letter and grouped by x); the ticks are small drawn shapes, found by position, not by
text. A name is printed level with its line, or centred beside two lines: a line belongs to the nearest name. Rows hold "<n> kcal" and no
other figure.

Source options (config/chains.yaml):
  labels       column label (a word of it) -> dictionary allergen column; labels that share a column ("Hazelnuts", "Almonds": treeNuts)
               name the nut in `treeNutSource`
  name_x1      right edge (pt) of the name column; serving_x0 the left edge of the "served" column
  kcal_x0      left edge of the calories column; marks_x0 the left edge of the allergen columns
  markers      {"": "No"}: the guide lists the allergens a modifier holds, so an unticked one is absent
A tick that is under no label, a line with no calories or no name, or text of another kind raises.
"""
import re
from pathlib import Path

import pdfplumber

LINE_GAP = 3
TICK = (5.0, 9.5)   # a tick is a drawn shape about 7 pt wide and tall; the page's logo shapes are larger or elsewhere
KCAL = re.compile(r"^(\d+)\s?kcal$")


def _centre(w: dict) -> float:
    return (w["top"] + w["bottom"]) / 2


def _lines(words: list[dict]) -> list[list[dict]]:
    out: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (_centre(w), w["x0"])):
        if out and _centre(w) - _centre(out[-1][0]) <= LINE_GAP:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(l, key=lambda w: w["x0"]) for l in out]


def _text(words: list[dict]) -> str:
    return " ".join(w["text"] for l in _lines(words) for w in l)


def _columns(chars: list[dict], labels: dict[str, str], page_no: int) -> list[tuple[float, str, str]]:
    """(x centre, label, dictionary column) for each rotated header label."""
    xs = sorted(chars, key=lambda c: (c["x0"] + c["x1"]) / 2)
    groups: list[list[dict]] = []
    for c in xs:
        if groups and (c["x0"] + c["x1"]) / 2 - (groups[-1][-1]["x0"] + groups[-1][-1]["x1"]) / 2 <= 6:
            groups[-1].append(c)
        else:
            groups.append([c])
    out = []
    for g in groups:
        by_x: dict[int, list[dict]] = {}
        for c in g:
            by_x.setdefault(round(c["x0"]), []).append(c)
        text = " ".join("".join(c["text"] for c in sorted(cs, key=lambda c: -c["top"])) for _, cs in sorted(by_x.items()))
        centre = sum((c["x0"] + c["x1"]) / 2 for c in g) / len(g)
        if text == "Calories":
            continue
        hit = next((labels[k] for k in labels if text.startswith(k)), None)
        if hit is None:
            raise ValueError(f"page {page_no}: the column label {text!r} is not in `labels`")
        out.append((centre, text, hit))
    return out


def parse_page(words: list[dict], chars: list[dict], shapes: list[dict], source: dict, page_no: int) -> list[dict]:
    name_x1, serving_x0, kcal_x0, marks_x0 = source["name_x1"], source["serving_x0"], source["kcal_x0"], source["marks_x0"]
    columns = _columns([c for c in chars if not c["upright"]], source["labels"], page_no)
    if not columns:
        raise ValueError(f"page {page_no}: no rotated column labels found")
    body = [w for w in words if w["upright"] and w["top"] >= source.get("body_top", 105) and w["bottom"] < source.get("body_bottom", 520)]
    lines = _lines(body)
    names, rows, section = [], [], ""
    for line in lines:
        left = [w for w in line if w["x1"] <= name_x1 and w["x0"] < name_x1]
        served = [w for w in line if serving_x0 <= w["x0"] < kcal_x0]
        kcal = [w for w in line if kcal_x0 <= w["x0"] < marks_x0]
        other = [w for w in line if w["x0"] >= marks_x0]
        if other:
            raise ValueError(f"page {page_no}: text in the allergen columns: {_text(other)!r}")
        text = _text(kcal)
        if not kcal:
            if left and not served:
                caps = _text(left)
                if caps.isupper():
                    section = caps
                else:
                    names.append((_centre(line[0]), caps))
                continue
            raise ValueError(f"page {page_no}: a line with no calories: {_text(line)[:50]!r}")
        m = KCAL.match(text.replace(" kcal", "kcal"))
        if not m:
            raise ValueError(f"page {page_no}: the calories {text!r} are not '<n> kcal'")
        if left:
            names.append((_centre(line[0]), _text(left)))
        rows.append({"y": _centre(line[0]), "served": _text(served), "kcal": m.group(1)})
    out = []
    for r in rows:
        if not names:
            raise ValueError(f"page {page_no}: a line with no name on the page")
        name = min(names, key=lambda n: abs(n[0] - r["y"]))[1]   # the name is printed level with its lines, or centred beside two of them
        row = {"Product_Name": name, "Category": section, "source_page": page_no, "energykCal_Per Portion": r["kcal"]}
        if r["served"]:
            row["Size"] = r["served"]
        marks = [s for s in shapes if abs((s["top"] + s["bottom"]) / 2 - r["y"]) <= 6]
        cells: dict[str, str] = {k: source.get("markers", {}).get("", "") for _, _, k in columns}
        nuts = []
        for s in marks:
            x = (s["x0"] + s["x1"]) / 2
            centre, label, col = min(columns, key=lambda c: abs(c[0] - x))
            if abs(centre - x) > 8:
                raise ValueError(f"page {page_no}, {name}: a tick at x={x:.0f} is under no label")
            cells[col] = "Yes"
            if col == "treeNuts":
                nuts.append(label)
        row |= cells
        if nuts:
            row["treeNutSource"] = ", ".join(nuts)
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
            page = doc.pages[n - 1]
            words = page.extract_words(extra_attrs=["fontname", "size", "upright"], x_tolerance=1.5, y_tolerance=1)
            shapes = [c for c in page.curves if TICK[0] <= c["x1"] - c["x0"] <= TICK[1] and TICK[0] <= c["bottom"] - c["top"] <= TICK[1] and c["top"] > 100]
            rows += parse_page(words, page.chars, shapes, source, n)
    return rows

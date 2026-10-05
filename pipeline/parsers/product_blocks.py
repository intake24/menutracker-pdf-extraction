"""Product blocks: a name (and diet tag) on the left, the ingredient declaration in the middle, a nutrition column on the right (Coffee #1 food).

Rows are the spaces between the table's horizontal rules (a product's name sits at the middle of a tall row, away from its nutrition column). Each row's nutrition column is: a run of labels (KJ, Kcal, Fat, Sat, Carbs, Sugar, Fibre, Protein, Salt) with a value
under "per 100g" and one under "per portion", then an optional "Portion weight (g)" line. Everything left of the nutrition column inside
that block's height belongs to the product: the larger type (`name_size`) is the name and diet tag, the smaller type is the
ingredient declaration, kept as printed. Allergens are the bold capital words of the declaration (WHEAT, MILK, ALMONDS) and the capital
words after "May contain"; a bold capital word that is not in the allergen words stops the run. Capital text outside any block is a
section heading; any other text outside a block raises.

Source options (config/chains.yaml):
  title_size     smallest type size (pt) of a section title
  name_size      smallest type size (pt) of a name or tag; the ingredient declaration is set smaller
  nutrition_x0   left edge (pt) of the nutrition column
  nutrients      printed label -> dictionary nutrient name; the two values of a line go to the columns "<name>_<base>" for `bases`
  bases          the two column bases, left to right ("Per 100g/ml", "Per Portion")
  rule_width     minimum width (pt) of a horizontal line that counts as a row rule (default 400)
  furniture      words that are page furniture above the table header (running heads, the page key)
  footer_word    the first word of the page footer (default Version): the last row ends there
  header_word    the table header's first title (default PRODUCT): its y is the top of the table
  diet_tags      the tags printed under a name, e.g. ["V", "Vg", "GF"]; "(V)" and "(Vg/GF)" go to `Diet` as printed
  may_phrases    phrases that start the list of what may be present (default ["May contain"]); capitals before the first one are allergens
  allergen_words extra allergen words (capitals) -> text for the allergen reader ("EGGS": "Egg"); "" for a word that only completes another ("SEEDS")
  markers        {"": "No"} when the guide says every allergen is in capitals, so an unmarked allergen is absent
A product with no name, no ingredients or a block with a missing value raises.
"""
import re
from pathlib import Path

import pdfplumber

from pipeline.allergens import parse_allergens

LINE_GAP = 3
NUT_NAMES = {"almond", "hazelnut", "walnut", "cashew", "pecan", "pistachio", "brazil", "macadamia"}
BASE_WORDS = {"wheat": "Wheat", "rye": "Rye", "barley": "Barley", "oats": "Oats", "oat": "Oats", "spelt": "Spelt", "milk": "Milk",
              "egg": "Egg", "eggs": "Egg", "soya": "Soya", "soy": "Soya", "sesame": "Sesame", "mustard": "Mustard", "celery": "Celery",
              "lupin": "Lupin", "fish": "Fish", "peanut": "Peanuts", "peanuts": "Peanuts", "sulphites": "Sulphites", "sulphite": "Sulphites",
              "gluten": "Gluten", "crustaceans": "Crustaceans", "molluscs": "Molluscs", "nuts": "Tree Nuts",
              "sulphur": "Sulphites", "metabisulphite": "Sulphites",
              "seeds": "", "tree": "", "dioxide": ""}   # "" : a word that only completes another ("SESAME SEEDS", "TREE NUTS", "SULPHUR DIOXIDE")


def _centre(w: dict) -> float:
    return (w["top"] + w["bottom"]) / 2


def _lines(words: list[dict]) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (_centre(w), w["x0"])):
        if lines and _centre(w) - _centre(lines[-1][0]) <= LINE_GAP:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _text(words: list[dict]) -> str:
    return " ".join(w["text"] for line in _lines(words) for w in line)


def _token(text: str) -> str:
    return text.strip(".,;:()[]*")


def _allergen_term(token: str, words: dict[str, str], page_no: int, product: str) -> str:
    low = token.lower()
    if low in words:
        return words[low]
    base = low[:-1] if low.endswith("s") else low
    if base in NUT_NAMES:
        return f"Tree Nuts ({base.title()})"
    raise ValueError(f"page {page_no}, {product}: the capital word {token!r} is not a known allergen word (list it under `allergen_words`)")


def _allergens(declaration: list[dict], source: dict, page_no: int, product: str) -> dict[str, str]:
    words = BASE_WORDS | {k.lower(): v for k, v in source.get("allergen_words", {}).items()}
    flat = [w for line in _lines(declaration) for w in line]
    texts = [_token(w["text"]).lower() for w in flat]
    phrases = [p.lower().split() for p in source.get("may_phrases", ["May contain"])]
    cut = min((i for i in range(len(texts)) for p in phrases
               if texts[i:i + len(p)] and len(texts[i:i + len(p)]) == len(p) and all(t.startswith(w) for t, w in zip(texts[i:i + len(p)], p))),
              default=len(flat))   # from here on the declaration lists what may be present
    contains, may = [], []
    for i, w in enumerate(flat):
        token = _token(w["text"])
        if len(token) < 3 or any(c.isdigit() for c in token):
            continue
        bold, capital = "Bold" in w["fontname"], token.isupper()
        if i < cut:
            # the declaration marks an allergen in bold capitals; a word of the allergen list that is only bold or only capitals counts too,
            # and a bold capital word that is not in the list stops the run
            known = token.lower() in words or token.lower().rstrip("s") in NUT_NAMES
            if not (bold and capital) and not known or not (bold or capital):
                continue
        elif not capital:
            continue
        term = _allergen_term(token, words, page_no, product)
        if term:   # "" marks a capital word that is part of an allergen's name ("SEEDS" in "SESAME SEEDS")
            (contains if i < cut else may).append(term)
    return parse_allergens(", ".join(dict.fromkeys(contains)), ", ".join(dict.fromkeys(may)), source.get("markers", {}).get("", ""))


def _block(words: list[dict], source: dict, page_no: int) -> dict | None:
    """The nutrition block of one row: label -> [per 100g, per portion], and the portion weight."""
    labels, nx0 = source["nutrients"], source["nutrition_x0"]
    area = [w for w in words if w["x0"] >= nx0]
    starts = [_centre(w) for w in area if w["text"] == "KJ"]
    if not starts:
        return None
    if len(starts) > 1:
        raise ValueError(f"page {page_no}: a row has {len(starts)} nutrition blocks")
    rows, weight = {}, None
    for line in _lines([w for w in area if _centre(w) >= starts[0] - 2]):
        label = line[0]["text"]
        values = [w["text"] for w in line[1:] if re.match(r"^<?\d[\d,]*(\.\d+)?$", w["text"])]
        if label in labels:
            if len(values) != 2:
                raise ValueError(f"page {page_no}: the nutrition line {' '.join(w['text'] for w in line)!r} does not have two values")
            rows[label] = values
        elif label == "Portion":
            if len(values) != 1:
                raise ValueError(f"page {page_no}: the portion weight line has {len(values)} values")
            weight = values[0]
    if "Salt" not in rows:
        raise ValueError(f"page {page_no}: a nutrition block does not reach Salt")
    return {"rows": rows, "weight": weight}


def parse_page(words: list[dict], rules: list[float], source: dict, page_no: int) -> list[dict]:
    """`rules`: the y of the table's horizontal rules (the first is the top of the header row, the second its bottom)."""
    name_size, title_size, nx0, labels = source["name_size"], source["title_size"], source["nutrition_x0"], source["nutrients"]
    furniture = set(source.get("furniture", ()))
    tag = re.compile(r"^\((?:%s)(?:[/,]\s*(?:%s))*\)$" % (("|".join(map(re.escape, source["diet_tags"])),) * 2))
    caps = lambda line: all(w["text"].replace("&", "A").isupper() for w in line)
    title = lambda line: all(w["size"] >= title_size for w in line)   # section titles are set larger than names
    anchor = source.get("header_word", "PRODUCT")
    header_y = min((_centre(w) for w in words if w["text"] == anchor), default=None)
    if header_y is None or len(rules) < 3:
        raise ValueError(f"page {page_no}: no table header or rules found")
    body = [r for r in rules if r > header_y]   # the rule under the header row and the rules between products
    # the page's section heading sits above the table header
    top = [line for line in _lines([w for w in words if _centre(w) < header_y - 2 and w["text"] not in furniture])]
    if any(not caps(line) for line in top):
        raise ValueError(f"page {page_no}: text above the table header that is not a heading: {' '.join(w['text'] for line in top for w in line)!r}")
    section = " ".join(" ".join(w["text"] for w in line) for line in top)
    note, upcoming = "", None   # a note printed under a heading; a section title printed at the foot of a row, for the header row after it
    out = []
    for lo, hi in zip(body, body[1:]):
        inside = [w for w in words if lo <= _centre(w) < hi]
        if any(w["text"] == anchor for w in inside):   # a header row in the middle of the page: the title before it is the new section
            if upcoming:
                section, note, upcoming = upcoming, "", None
            continue
        block = _block(inside, source, page_no)
        left = [w for w in inside if w["x0"] < nx0]
        if block is None:   # a heading row (capitals), perhaps with a note under it
            lines = _lines(left)
            titles = [l for l in lines if title(l)]
            if titles:
                section, note = " ".join(_text(l) for l in titles), ""
            if [l for l in lines if not title(l)]:
                note = _text([w for l in lines if not title(l) for w in l])
            continue
        # capital-only lines below the nutrition block are the title of the next section
        foot = max(_centre(w) for w in inside if w["x0"] >= nx0)
        titles = [l for l in _lines(left) if title(l) and _centre(l[0]) > foot + 2 and all(w["text"] not in furniture for w in l)]
        if titles:
            upcoming = " ".join(_text(l) for l in titles)
            gone = {id(w) for l in titles for w in l}
            left = [w for w in left if id(w) not in gone]
        product = [w for w in left if w["size"] >= name_size]       # names and tags are set larger than the declaration
        declaration = [w for w in left if w["size"] < name_size]
        name_lines, tags = [], []
        for line in _lines(product):
            text = " ".join(w["text"] for w in line)
            (tags if tag.match(text) else name_lines).append(text)
        if not name_lines or not declaration:
            raise ValueError(f"page {page_no}: the product row at y={lo:.0f} has no {'name' if not name_lines else 'ingredients'}")
        name = " ".join(name_lines)
        row = {"Product_Name": name, "Category": section, "source_page": page_no}
        if tags:
            row["Diet"] = " ".join(tags)
        if note:
            row["notes"] = note
        row["Ingredients"] = _text(declaration)
        for label, nutrient in labels.items():
            if label in block["rows"]:
                for base, value in zip(source["bases"], block["rows"][label]):
                    row[f"{nutrient}_{base}"] = value
        if block["weight"]:
            row |= {"Serving_Size": block["weight"], "Serving_Size_Unit": "g"}
        out.append(row | _allergens(declaration, source, page_no, name))
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
            words = page.extract_words(extra_attrs=["fontname", "size"], x_tolerance=1.5, y_tolerance=1)
            wide = source.get("rule_width", 400)
            rules = sorted({round(e["top"]) for e in page.edges if e["orientation"] == "h" and e["x1"] - e["x0"] >= wide})
            foot = min((w["top"] for w in words if w["text"] == source.get("footer_word", "Version")), default=page.height)
            rows += parse_page(words, rules + [round(foot) - 1], source, n)   # the last row of a page has no rule under it: it ends at the footer
    return rows

"""Allergen matrix pages and nutrition pages that list the same products: each pair is read by the model and joined row by row.

Used where one product's diet choices and ticked allergens are on one page and its figures on another (Krispy Kreme).
The model only transcribes: every matrix row (name, YES/NO diet cells, the printed headers of the ticked columns) and every
nutrition row (name, weight, figures). Code maps ticks and figures to dictionary columns, pairs rows in page order, and
stops when the two pages have different numbers of rows or a pair of names is not alike; names that differ a little are
flagged (the nutrition page's name is kept). An unknown tick header or diet word stops the run.

Source options (config/chains.yaml):
  joins         [{matrix: [pages], nutrition: [pages]}]: the rows of the matrix pages, in order, are paired with the rows of the
                nutrition pages, in order (one matrix page may serve several nutrition pages; `nutrition: []` keeps the
                matrix rows alone). Optional: matrix_section / nutrition_section / matrix_name (regular expressions: only rows under a
                matching heading, or with a matching name), by_name (each nutrition row gets the allergen row of the same drink; the size and any
                bracketed note are ignored, and allergen rows without a nutrition row are kept with a warning)
  fields        key the model returns for a figure -> dictionary column; "weight" is the portion weight and is split into
                Serving_Size / Serving_Size_Unit
  tick_labels   printed allergen column header -> dictionary column
  markers       {"✓": "Yes", "": ""}: a tick is Yes; a blank cell is left blank unless the key says what it means
  instructions  what the pages look like
  dpi           render resolution (default 200)
Rows carry method "llm".
"""
import difflib
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pipeline import llm
from pipeline.parsers import vision_table

WORK = vision_table.WORK
RUNNER = llm.claude_runner          # tests replace these two
BUDGET = llm.BUDGET
WORKERS = 3
DIET = {"vegetarian": "Suitable_for_Vegetarian", "vegan": "Suitable_for_Vegan", "halal": "Suitable_for_Halal"}
MAX_WARNINGS = 3                     # names that differ on this many rows of one join: the rows are probably shifted
SAME, ALIKE = 0.85, 0.4              # name similarity: no flag at or above SAME, a flag at or above ALIKE, a stop below


def _schema(extra: dict, name_keys: list[str]) -> dict:
    props = {k: {"type": "string"} for k in ["section", "name", "note", *name_keys]} | extra
    return {"type": "object", "required": ["rows"], "properties": {"rows": {"type": "array", "items": {
        "type": "object", "required": ["name"], "properties": props}}}}


def matrix_schema() -> dict:
    return _schema({"ticks": {"type": "array", "items": {"type": "string"}}}, [*DIET, "tree_nut_source"])


def nutrition_schema(fields: dict) -> dict:
    return _schema({}, ["weight", *fields])


def check_answer(answer: dict, page_no: int) -> None:
    if not isinstance(answer.get("rows"), list) or not answer["rows"]:
        raise llm.LlmError(f"page {page_no}: the model returned no rows (list only matrix and nutrition pages under `joins`)")


def kinds(source: dict) -> dict[int, str]:
    out: dict[int, str] = {}
    for j in source["joins"]:
        for kind in ("matrix", "nutrition"):
            for p in j[kind]:
                if out.setdefault(p, kind) != kind:
                    raise llm.LlmError(f"page {p} is listed as both a matrix and a nutrition page")
    return out


def pages_of(pdf: Path, source: dict) -> list[int]:
    return sorted(kinds(source))


def raw_rows(pdf: Path, source: dict, page_no: int, pages_dir: Path | None = None) -> list[dict]:
    """The model's rows for one page, as it returned them."""
    kind = kinds(source)[page_no]
    pages_dir = pages_dir or WORK / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    stem = pages_dir / f"{pdf.stem}-{page_no}"
    subprocess.run(["pdftoppm", "-r", str(source.get("dpi", 200)), "-f", str(page_no), "-l", str(page_no),
                    "-png", "-singlefile", str(pdf), str(stem)], check=True)
    png = stem.with_suffix(".png")
    if kind == "matrix":
        schema = matrix_schema()
        ask = ("Return EVERY product row of the allergen table, in order. section = the grey heading above the rows. name = "
               "the bold product name; note = the italic line under it in brackets, else empty. vegetarian, vegan, halal = "
               "the YES or NO in the three Dietary Choices cells. ticks = the printed column header of every allergen "
               "cell that holds a tick, copied exactly as printed (for example 'Wheat', 'Egg / Egg Products'); the "
               "tick can be anywhere in the 'Cereals containing Gluten' and 'Allergen Present / Contains' columns. "
               "tree_nut_source = the small text in the last column, else empty.")
    else:
        schema = nutrition_schema(source["fields"])
        keys = ", ".join(source["fields"])
        ask = ("Return EVERY product row of the nutrition table, in order. section = the grey heading above the rows. "
               f"name = the bold product name; note = the italic line under it in brackets, else empty. weight = the "
               f"'Average Portion weight' cell with its unit (51g, 227 ml). Figures, as the keys {keys}: the cells "
               "left to right, 'Nutrition Per 100g' (or 100 ml) first, then 'Nutrition Per Portion'; a cell that holds "
               "words instead of figures is left empty.")
    prompt = (f"Read the image {png}. {source['instructions']} {ask} Copy every cell exactly as printed, as a string; use an "
              "empty string for a blank cell. Do not correct, convert or calculate anything.")
    answer = llm.call(prompt, schema, png, runner=RUNNER, cache_dir=WORK / "llm", budget=BUDGET,
                      validate=lambda a: check_answer(a, page_no))
    return answer["rows"]


def _name(item: dict) -> str:
    return " ".join(x for x in ((item.get("name") or "").strip(), (item.get("note") or "").strip()) if x)


def matrix_cells(item: dict, source: dict, page_no: int) -> dict:
    cells = {}
    for key, column in DIET.items():
        value = (item.get(key) or "").strip()
        if value and value.casefold() not in ("yes", "no"):
            raise llm.LlmError(f"page {page_no}, {_name(item)}: {key} is {value!r}, expected YES or NO")
        if value:
            cells[column] = value
    labels = {k.casefold(): v for k, v in source["tick_labels"].items()}
    for tick in item.get("ticks") or []:
        if tick.casefold().strip() not in labels:
            raise llm.LlmError(f"page {page_no}, {_name(item)}: the tick header {tick!r} is not in tick_labels")
        cells[labels[tick.casefold().strip()]] = source["markers"]["✓"]
    if text := (item.get("tree_nut_source") or "").strip():
        cells["treeNutSource"] = text
    return cells


def nutrition_cells(item: dict, source: dict) -> dict:
    cells = {}
    if weight := (item.get("weight") or "").strip():
        m = vision_table.PORTION.match(weight)
        cells |= {"Serving_Size": m.group(1), "Serving_Size_Unit": m.group(2)} if m else {"Portion_Size": weight}
    for key, column in source["fields"].items():
        if value := (item.get(key) or "").strip():
            cells[column] = value
    return cells


def _core(name: str) -> str:
    """A name for comparing: no bracketed notes, no size at the end ("12oz", "340 ml"), only letters and digits."""
    name = re.sub(r"\(.*?\)", " ", name)
    name = re.sub(r"\s*\b\d+\s*(?:oz|ml)\s*$", "", name, flags=re.I)
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def _alike(a: str, b: str) -> float:
    a, b = _core(a), _core(b)
    if a == b:
        return 1.0
    if a and b and (a.startswith(b) or b.startswith(a)):   # "Latte" and "Latte made with Biscoff sauce"
        return ALIKE
    return difflib.SequenceMatcher(None, a, b).ratio()


def _pair_by_name(matrix: list[dict], nutrition: list[dict], page_no: int) -> tuple[list[tuple[dict, dict]], list[dict]]:
    """Every nutrition row (a drink in one size) with the allergen row of the same drink; allergen rows nobody used are returned too."""
    by_core = {}
    for m in matrix:
        core = _core(m.get("name") or "")
        if core in by_core:
            raise llm.LlmError(f"page {page_no}: two allergen rows have the same name once notes and sizes are ignored: "
                               f"{by_core[core].get('name')!r} and {m.get('name')!r}; select one with matrix_name")
        by_core[core] = m
    pairs, used = [], set()
    for n in nutrition:
        m = by_core.get(_core(n.get("name") or ""))
        if m is None:
            raise llm.LlmError(f"page {n.get('_page', page_no)}: no allergen row for the nutrition row {n.get('name')!r}")
        used.add(id(m))
        pairs.append((m, n))
    return pairs, [m for m in matrix if id(m) not in used]


def _warn(row: dict, text: str) -> None:
    row["flags"] = (row["flags"] + " | " if row.get("flags") else "") + f"warn: {text}"


def _check_tree_nuts(row: dict) -> None:
    if row.get("treeNutSource") and row.get("treeNuts") != "Yes":
        _warn(row, f"a tree nut source ({row['treeNutSource']!r}) is printed without the Tree Nuts tick")


def _joined(m: dict, n: dict, source: dict, page_no: int, check_names: bool = True) -> dict:
    name = _name(n)
    if not (n.get("name") or "").strip():
        raise llm.LlmError(f"page {page_no}: the model returned a row without a name: {n!r}")
    score = _alike(m.get("name") or "", n["name"]) if check_names else 1.0
    if score < ALIKE:
        raise llm.LlmError(f"page {page_no}: the allergen row {m.get('name')!r} and the nutrition row {n['name']!r} are not the same product")
    row = {"Product_Name": name, "Category": (n.get("section") or "").strip(), "source_page": page_no, "method": "llm"}
    row |= matrix_cells(m, source, page_no) | nutrition_cells(n, source)
    if score < SAME:
        _warn(row, f"the allergen page calls this {_name(m)!r}, the nutrition page {name!r}")
    _check_tree_nuts(row)
    return row


def _key(row: dict) -> tuple:
    return row.get("_page"), row.get("_i")


def join_rows(matrix: list[dict], nutrition: list[dict], source: dict, page_no: int, by_name: bool = False,
              ledger: dict | None = None) -> list[dict]:
    """Rows of the nutrition page(s) joined with the matrix page(s)' diet cells and ticks: in order, or (`by_name`) each
    nutrition row with the allergen row of the same drink. By name, allergen rows nobody used (printed, but with no figures)
    are kept with a warning, or (with a `ledger`) handed back in ledger["unused"] so a caller can keep each once."""
    if by_name:
        pairs, unused = _pair_by_name(matrix, nutrition, page_no)
        rows = [_joined(m, n, source, n.get("_page", page_no), check_names=False) for m, n in pairs]
        if ledger is not None:
            ledger.setdefault("paired", set()).update(_key(m) for m, _ in pairs)
            ledger.setdefault("unused", {}).update({_key(m): m for m in unused})
        else:
            rows += [_leftover(m, source, page_no) for m in unused]
        return rows
    if len(matrix) != len(nutrition):
        raise llm.LlmError(f"page {page_no}: the allergen page(s) have {len(matrix)} rows, the nutrition page(s) {len(nutrition)} rows; "
                           f"check the joins in config/chains.yaml")
    rows = [_joined(m, n, source, n.get("_page", page_no)) for m, n in zip(matrix, nutrition)]
    if sum("the allergen page calls" in r.get("flags", "") for r in rows) >= MAX_WARNINGS:
        raise llm.LlmError(f"page {page_no}: the names differ on {MAX_WARNINGS} or more rows of this join; the rows are probably shifted "
                           f"(a row missing or extra on one of the pages)")
    return rows


def _leftover(m: dict, source: dict, page_no: int) -> dict:
    row = matrix_only_rows([m], source, m.get("_page", page_no))[0]
    _warn(row, "no row for this product on the nutrition pages")
    return row


def matrix_only_rows(matrix: list[dict], source: dict, page_no: int) -> list[dict]:
    """Rows of a matrix page that has no nutrition page (a `joins` entry with `nutrition: []`)."""
    rows = [{"Product_Name": _name(m), "Category": (m.get("section") or "").strip(), "source_page": m.get("_page", page_no),
             "method": "llm"} | matrix_cells(m, source, page_no) for m in matrix]
    for row in rows:
        _check_tree_nuts(row)
    return rows


def page_rows(pdf: Path, source: dict, page_no: int, pages_dir: Path | None = None) -> list[dict]:
    """One page on its own (for `pages` and `reread`): diet and allergen cells for a matrix page, figures for a nutrition page."""
    kind = kinds(source)[page_no]
    out = []
    for item in raw_rows(pdf, source, page_no, pages_dir):
        cells = matrix_cells(item, source, page_no) if kind == "matrix" else nutrition_cells(item, source)
        out.append({"Product_Name": _name(item), "Category": (item.get("section") or "").strip(),
                    "source_page": page_no, "method": "llm"} | cells)
    return out


def _select(rows: list[dict], pattern: str | None, what: str, page_no: int, field: str = "section") -> list[dict]:
    """Rows whose section heading (or name) matches the join's regular expression (all rows without one)."""
    if not pattern:
        return rows
    chosen = [r for r in rows if re.search(pattern, r.get(field) or "", re.I)]
    if not chosen:
        raise llm.LlmError(f"page {page_no}: no {what} rows with a {field} matching {pattern!r}")
    return chosen


def parse(pdf: Path, source: dict) -> list[dict]:
    pages = pages_of(pdf, source)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:   # one read per page, even when joins share a page
        read = dict(zip(pages, pool.map(lambda p: raw_rows(pdf, source, p), pages)))
    rows, consumed, ledger = [], set(), {}
    for j in source["joins"]:
        page_no = (j["nutrition"] or j["matrix"])[-1]
        matrix = _select([r | {"_page": p, "_i": i} for p in j["matrix"] for i, r in enumerate(read[p])], j.get("matrix_section"), "allergen", page_no)
        matrix = _select(matrix, j.get("matrix_name"), "allergen", page_no, "name")
        nutrition = _select([r | {"_page": p, "_i": i} for p in j["nutrition"] for i, r in enumerate(read[p])], j.get("nutrition_section"), "nutrition", page_no)
        consumed |= {_key(r) for r in matrix + nutrition}
        rows += join_rows(matrix, nutrition, source, page_no, j.get("by_name", False), ledger) if nutrition else matrix_only_rows(matrix, source, page_no)
    rows += [_leftover(m, source, 0) for k, m in sorted(ledger.get("unused", {}).items()) if k not in ledger.get("paired", set())]
    missed = [(p, r.get("section"), r["name"]) for p in pages for i, r in enumerate(read[p]) if (p, i) not in consumed]
    if missed:
        raise llm.LlmError(f"{len(missed)} rows read from the pages are used by no join, e.g. {missed[:3]}; fix the section/name patterns in `joins`")
    return rows


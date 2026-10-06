"""Pages whose text layer is unusable (a corrupt embedded font drops digits): the page image is read by the model.

Each page is rendered to work/pages/ and read with one `claude -p` call that must return every row as strings, copied
exactly as printed. The model only transcribes: the portion cell is split into Serving_Size / Serving_Size_Unit here
in code, and every value then goes through the same dictionary and arithmetic checks as a parsed row (problems are
flagged, never corrected).

Source options (config/chains.yaml):
  fields        key the model returns -> dictionary column (the nutrient cells, left to right as on the page)
  instructions  what the page looks like: which text is the section, the item name, the size line
  pages         pages to read: numbers and "a-b" ranges (default: every page)
  dpi           render resolution (default 110)
  text_check    {field, pattern, ignore, page_ignore {page: [figures]}, strip, tags: {field, pattern, keep}}: for pages whose text layer prints its figures, every printed figure must be a row the model read and the
                other way round (a dish left out or invented stops the run; the answer is not cached)
Rows carry method "llm".
"""
import re
import subprocess
from pathlib import Path

from pipeline import llm
from pipeline.ingest import page_texts

WORK = Path(__file__).resolve().parent.parent.parent / "work"
PORTION = re.compile(r"^(\d+(?:\.\d+)?)\s*(g|ml)$")
RUNNER = llm.runner          # tests replace these two
BUDGET = llm.BUDGET


def schema_for(fields: dict[str, str]) -> dict:
    keys = ["section", "name", "size", "portion", *fields]
    return {"type": "object", "required": ["rows"], "properties": {"rows": {"type": "array", "items": {
        "type": "object", "required": ["name"], "properties": {k: {"type": "string"} for k in keys}}}}}


def check_answer(answer: dict, page_no: int) -> None:
    """A page of table rows with no rows means the model didn't read it, not that the page is empty."""
    if not isinstance(answer.get("rows"), list) or not answer["rows"]:
        raise llm.LlmError(f"page {page_no}: the model returned no rows")


def check_text_figures(answer: dict, text: str, spec: dict, page_no: int) -> None:
    """A page whose text layer prints its figures (menus: "(485kcal)"): every printed figure must be a row the model read and every figure
    the model read must be printed, counted as a multiset; an answer that fails is never cached."""
    from collections import Counter
    ignore = {str(x) for x in spec.get("ignore", ())} | {str(x) for x in (spec.get("page_ignore") or {}).get(str(page_no), ())}
    strip = str(spec.get("strip", ""))
    clean = lambda v: "".join(c for c in v if c not in strip)   # "1,706" is 1706
    printed = Counter(c for c in (clean(v) for v in re.findall(spec["pattern"], text, re.I)) if c not in ignore)
    read = Counter(clean((r.get(spec["field"]) or "").strip()) for r in answer["rows"])
    read = Counter({k: v for k, v in read.items() if k and k not in ignore})
    if printed != read:
        raise llm.LlmError(f"page {page_no}: the text layer prints {sorted((printed - read).elements())} that the model did not read, and the model read "
                           f"{sorted((read - printed).elements())} that the page does not print")
    if tags := spec.get("tags"):   # the tags printed right before a figure: where the text layer shows them for every use of the figure, the row's must be one of them
        shown: dict[str, list[str]] = {}
        for m in re.finditer(tags["pattern"], text):
            printed_tags = m.group(1).split()
            if keep := tags.get("keep"):   # only these tags are read (the others, e.g. beer pairings, are not part of the row)
                printed_tags = [x for x in printed_tags if re.fullmatch(keep, x)]
            shown.setdefault(m.group(2), []).append(" ".join(printed_tags))
        for r in answer["rows"]:
            figure, got = (r.get(spec["field"]) or "").strip(), (r.get(tags["field"]) or "").strip()
            options = shown.get(figure, [])
            if options and all(options) and got not in options:
                raise llm.LlmError(f"page {page_no}: the row with {figure} has the tags {got!r}, the text layer prints {options}")


def rows_from_answer(answer: dict, fields: dict[str, str], page_no: int) -> list[dict]:
    check_answer(answer, page_no)
    rows = []
    for item in answer["rows"]:
        name = (item.get("name") or "").strip()
        if not name:
            raise llm.LlmError(f"page {page_no}: the model returned a row without a name: {item!r}")
        row = {"Product_Name": name, "Category": (item.get("section") or "").strip(), "source_page": page_no,
               "method": "llm"}
        if size := (item.get("size") or "").strip():
            row["Size"] = size
        if portion := (item.get("portion") or "").strip():
            m = PORTION.match(portion)
            row |= {"Serving_Size": m.group(1), "Serving_Size_Unit": m.group(2)} if m else {"Portion_Size": portion}
        for key, column in fields.items():
            if value := (item.get(key) or "").strip():
                row[column] = value
        rows.append(row)
    return rows


def page_rows(pdf: Path, source: dict, page_no: int, pages_dir: Path | None = None) -> list[dict]:
    """One page's rows. `pages_dir` lets a re-read render elsewhere so the images of the real run are never touched."""
    fields, schema = source["fields"], schema_for(source["fields"])
    pages_dir = pages_dir or WORK / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    stem = pages_dir / f"{pdf.stem}-{page_no}"
    subprocess.run(["pdftoppm", "-r", str(source.get("dpi", 110)), "-f", str(page_no), "-l", str(page_no),
                    "-png", "-singlefile", str(pdf), str(stem)], check=True)
    png = Path(f"{stem}.png")   # not with_suffix: a name like 04.25-menu has a dot
    prompt = (f"Read the image {png}. {source['instructions']} Return EVERY data row on the page, in order. "
              "Copy every cell exactly as printed, as a string, including words like Trace and typos; use an "
              "empty string for a blank cell. Do not correct, convert or calculate anything.")
    def validate(a: dict) -> None:
        check_answer(a, page_no)
        if spec := source.get("text_check"):
            check_text_figures(a, page_texts(pdf)[page_no - 1], spec, page_no)
    answer = llm.call(prompt, schema, png, runner=RUNNER, cache_dir=WORK / "llm", budget=BUDGET, validate=validate)
    return rows_from_answer(answer, fields, page_no)


def pages_of(pdf: Path, source: dict) -> list[int]:
    if "pages" in source:   # numbers and "a-b" ranges: a cover or a page with no table is left out
        out: list[int] = []
        for item in source["pages"]:
            a, _, b = str(item).partition("-")
            out += range(int(a), int(b or a) + 1)
        return out
    return list(range(1, len(page_texts(pdf)) + 1))


def parse(pdf: Path, source: dict) -> list[dict]:
    return [row for n in pages_of(pdf, source) for row in page_rows(pdf, source, n)]

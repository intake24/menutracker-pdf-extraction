"""Pages whose text layer is unusable (a corrupt embedded font drops digits): the page image is read by the model.

Each page is rendered to work/pages/ and read with one `claude -p` call that must return every row as strings, copied
exactly as printed. The model only transcribes: the portion cell is split into Serving_Size / Serving_Size_Unit here
in code, and every value then goes through the same dictionary and arithmetic checks as a parsed row (problems are
flagged, never corrected).

Source options (config/chains.yaml):
  fields        key the model returns -> dictionary column (the nutrient cells, left to right as on the page)
  instructions  what the page looks like: which text is the section, the item name, the size line
  dpi           render resolution (default 110)
Rows carry method "llm".
"""
import re
import subprocess
from pathlib import Path

from pipeline import llm
from pipeline.ingest import page_texts

WORK = Path(__file__).resolve().parent.parent.parent / "work"
PORTION = re.compile(r"^(\d+(?:\.\d+)?)\s*(g|ml)$")
RUNNER = llm.claude_runner          # tests replace these two
BUDGET = llm.BUDGET


def schema_for(fields: dict[str, str]) -> dict:
    keys = ["section", "name", "size", "portion", *fields]
    return {"type": "object", "required": ["rows"], "properties": {"rows": {"type": "array", "items": {
        "type": "object", "required": ["name"], "properties": {k: {"type": "string"} for k in keys}}}}}


def check_answer(answer: dict, page_no: int) -> None:
    """A page of table rows with no rows means the model didn't read it, not that the page is empty."""
    if not isinstance(answer.get("rows"), list) or not answer["rows"]:
        raise llm.LlmError(f"page {page_no}: the model returned no rows")


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
    png = stem.with_suffix(".png")
    prompt = (f"Read the image {png}. {source['instructions']} Return EVERY data row on the page, in order. "
              "Copy every cell exactly as printed, as a string, including words like Trace and typos; use an "
              "empty string for a blank cell. Do not correct, convert or calculate anything.")
    answer = llm.call(prompt, schema, png, runner=RUNNER, cache_dir=WORK / "llm", budget=BUDGET,
                      validate=lambda a: check_answer(a, page_no))
    return rows_from_answer(answer, fields, page_no)


def pages_of(pdf: Path, source: dict) -> list[int]:
    return list(range(1, len(page_texts(pdf)) + 1))


def parse(pdf: Path, source: dict) -> list[dict]:
    return [row for n in pages_of(pdf, source) for row in page_rows(pdf, source, n)]

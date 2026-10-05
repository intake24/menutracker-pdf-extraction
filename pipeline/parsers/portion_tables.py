"""Nutrition tables whose rows sit under product titles, with several tables of different widths on one page (Pizza Hut).

A page is a list of lines: column-header lines (every word is in `header_words`), furniture (starts with a `furniture`
text), data rows (a name followed by numbers) and other text. Other text directly above a data row is that row's title;
other text above more text, a header or the end of the page is a section heading (headings in a row make one category, joined
with " - "), which persists (also onto the next page) until the next one. What a title means depends on the table, which is found by how many numbers its rows have:

  shapes   {number of cells: {columns, title, category, extra}}
           columns   the dictionary column of each numeric cell, left to right
           title     "product": the title is the product and the row's own text is its Size (pizza blocks: "Veggie
                     Supreme" over "Individual Pan (9")"); "section": the title is the category and the row's text is
                     the product
           category  the category before any section heading is seen (default empty)
           extra     columns added to every row of the table, e.g. {Serving_Size_Unit: g}
  header_words  the words column headers are made of (an unknown word makes the line a title, so list them all)
  furniture     lines starting with one of these texts (page headings, notes) are ignored
  pages         pages to read: numbers and "a-b" ranges

A row with a number of cells that fits no shape, or a size row with no title above it, raises.
"""
import re
from pathlib import Path

from pipeline.ingest import page_words_fine
from pipeline.parsers.numeric_table import MIN_NUMBERS, NUMBER, _lines, _split


def expand_pages(spec: list) -> list[int]:
    out: list[int] = []
    for item in spec:
        a, _, b = str(item).partition("-")
        out += range(int(a), int(b or a) + 1)
    return out


def parse_pages(pages: list[list], source: dict, numbers: list[int]) -> list[dict]:
    vocab = {w.casefold() for w in source["header_words"]}
    furniture = tuple(source.get("furniture", ()))
    shapes = {int(k): v for k, v in source["shapes"].items()}
    rows: list[dict] = []
    section = None
    for page_no in numbers:
        items = []   # (kind, text, cells)
        for line in _lines(pages[page_no - 1]):
            name, cells = _split(line, NUMBER)
            text = " ".join(w.text for w in (name or line))
            if name and len(cells) >= MIN_NUMBERS:
                items.append(("row", text, [w.text for w in cells]))
            elif text.startswith(furniture):
                continue
            elif all(w.text.casefold() in vocab for w in line):
                items.append(("header", text, []))
            else:
                items.append(("text", text, []))
        title, run = None, False   # run: the line above was a section heading too (headings in a row make one category)
        for i, (kind, text, cells) in enumerate(items):
            if kind == "header":
                title, run = None, False
            elif kind == "text":
                following = items[i + 1][0] if i + 1 < len(items) else None
                if following == "row" and shapes.get(len(items[i + 1][2]), {}).get("title") == "product":
                    title, run = text, False
                else:
                    section, title, run = (f"{section} - {text}" if run else text), None, True
            else:
                run = False
                shape = shapes.get(len(cells))
                if shape is None:
                    raise ValueError(f"page {page_no}: {text!r} has {len(cells)} numbers, which fits none of the shapes {sorted(shapes)}")
                if shape["title"] == "product":
                    if title is None:
                        raise ValueError(f"page {page_no}: the row {text!r} has no product title above it")
                    row = {"Product_Name": title, "Size": text}
                else:
                    row = {"Product_Name": text}
                row |= {"Category": section or shape.get("category", ""), "source_page": page_no}
                row |= shape.get("extra", {}) | dict(zip(shape["columns"], cells))
                if len(cells) != len(shape["columns"]):
                    raise ValueError(f"page {page_no}: shape {len(cells)} names {len(shape['columns'])} columns")
                rows.append(row)
    return rows


def parse(pdf: Path, source: dict) -> list[dict]:
    return parse_pages(page_words_fine(pdf), source, expand_pages(source["pages"]))

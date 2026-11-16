"""Free second check for a model-read PDF that has an intact text layer: every numeric figure of every output row of that PDF must be a token of the text of the row's page.

Usage: python tools/figcheck.py outputs/<id>_<Chain>.csv inputs/<file>.pdf

It prints each row with a figure that is not on its page, then a summary line. A figure split over two text lines ("220." / "8") or printed with a space ("0 .39") shows up here and needs a look at the page; a real misread (Papa John's 12.5 for 12.6, September 2026) shows up the same way. Does not apply to PDFs with a corrupt text layer (Vue) or no text layer (images).
"""
import collections
import csv
import re
import subprocess
import sys

SKIP = {"item_name", "menu_section", "source_file", "source_page", "method", "flags", "region", "Size", "servingsize", "servingsizeunit", "notes", "Diet", "Ingredients"}


def main(csv_path: str, pdf: str) -> int:
    name = pdf.split("/")[-1]
    rows = [r for r in csv.DictReader(open(csv_path)) if r["source_file"] == name]
    cache: dict[int, collections.Counter] = {}

    def tokens(page: int) -> collections.Counter:
        if page not in cache:
            text = subprocess.run(["pdftotext", "-layout", "-f", str(page), "-l", str(page), pdf, "-"], capture_output=True, text=True).stdout
            text = re.sub(r"(?<=\d),(?=\d{3})", "", text)   # thousands commas
            cache[page] = collections.Counter(re.findall(r"<?\d+(?:\.\d+)?", text))
        return cache[page]

    bad = total = 0
    for r in rows:
        page_tokens, missing = tokens(int(r["source_page"])), []
        for column, value in r.items():
            if column in SKIP or not value or not re.fullmatch(r"<?\d+(?:\.\d+)?", value):
                continue
            total += 1
            plain = value.lstrip("<")
            trimmed = value.rstrip("0").rstrip(".") if "." in value else value
            if value not in page_tokens and plain not in page_tokens and trimmed not in page_tokens:
                missing.append((column, value))
        if missing:
            bad += 1
            print(r["source_page"], r["item_name"][:40], missing[:4])
    print(f"rows {len(rows)} figures {total} rows with a figure not on the page text: {bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))

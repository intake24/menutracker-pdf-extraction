"""Check a source without ground truth: does every data-looking line of the PDF's text layer have a row?

Pearl Scan is not there for new batches, so each text-layer source is also compared with an independent count: the
lines of `pdftotext -layout` that carry at least `min_numbers` numeric tokens (data rows, plus a few headers and notes)
against the rows the parser produced from that page. A page with fewer rows than data-looking lines is a place a row
could have been lost; the report lists it for a person to look at. A page with more rows is expected for tables where
one printed line holds one row, so only shortfalls count.
"""
import re
from collections import Counter
from pathlib import Path

from pipeline.ingest import page_texts

TOKEN = re.compile(r"^[<\d][\d.,]*$|^(?:Negligible|Traces?|Tr|Trace|#N/A)$")


def numeric_lines(pdf: Path, min_numbers: int) -> dict[int, int]:
    """page number (1-based) -> lines with at least `min_numbers` numeric tokens."""
    out = {}
    for n, text in enumerate(page_texts(pdf), start=1):
        count = sum(sum(bool(TOKEN.match(t)) for t in line.split()) >= min_numbers for line in text.splitlines())
        if count:
            out[n] = count
    return out


def shortfalls(rows: list[dict], lines: dict[int, int]) -> dict[int, tuple[int, int]]:
    """page -> (rows, data-looking lines) where the page has fewer rows than lines."""
    have = Counter(r["source_page"] for r in rows)
    return {p: (have[p], n) for p, n in lines.items() if have[p] < n}


def page_gaps(rows: list[dict], lines: dict[int, int], slack: float = 0.75) -> dict[int, tuple[int, int]]:
    """page -> (rows, rows expected) for any text-layer layout, not only one data line per row.

    A source has a typical number of data-looking lines per row (1 for a plain table, 9 for blocks with a figure column); the
    expected rows of a page are its lines divided by that typical ratio (the median over the source's pages). A page that has
    `slack` of a row or more fewer than expected is listed (one lost row on a page is enough). A merged row ("17, 2") counts on each of its pages."""
    have: Counter = Counter()
    for r in rows:
        for page in str(r["source_page"]).split(","):
            have[int(page)] += 1
    ratios = sorted(n / have[p] for p, n in lines.items() if have[p])
    if not ratios:
        return {}
    typical = ratios[len(ratios) // 2]
    gaps = {}
    for p, n in lines.items():
        expected = n / typical
        if expected - have[p] >= slack:
            gaps[p] = (have[p], round(expected))
    return gaps

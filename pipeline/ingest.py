import hashlib
import html
import re
import subprocess
from pathlib import Path
from typing import NamedTuple

import pdfplumber
import yaml

CHAINS_FILE = Path(__file__).resolve().parent.parent / "config" / "chains.yaml"
IMAGE_PAGE_MAX_CHARS = 200  # non-whitespace chars; below this the page is treated as image-only
WORD = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>')


class Word(NamedTuple):
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


def page_texts(pdf: Path) -> list[str]:
    """Layout-preserving text, one string per page (pdftotext ends every page with a form feed)."""
    out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                         check=True, capture_output=True, text=True).stdout
    return out.split("\f")[:-1]


def page_words(pdf: Path) -> list[list[Word]]:
    """Every word with its bounding box (points, origin top-left), one list per page."""
    out = subprocess.run(["pdftotext", "-bbox", str(pdf), "-"],
                         check=True, capture_output=True, text=True).stdout
    return [[Word(float(a), float(b), float(c), float(d), html.unescape(t)) for a, b, c, d, t in WORD.findall(page)]
            for page in out.split("<page ")[1:]]


NUMERIC_CHARS = re.compile(r"^[\d.<]+$")


def page_words_fine(pdf: Path, gap: float = 0.5) -> list[list[Word]]:
    """Words like page_words, but runs of digits are split wherever two characters are more than `gap` pt apart."""
    out = []
    with pdfplumber.open(pdf) as doc:
        for page in doc.pages:
            coarse = page.extract_words(x_tolerance=3, y_tolerance=3)
            fine = page.extract_words(x_tolerance=gap, y_tolerance=3)
            by_line: dict[int, list] = {}   # fine words bucketed by the whole-point row of their top edge
            for f in fine:
                by_line.setdefault(int(f["top"]), []).append(f)
            words = []
            for w in coarse:
                if NUMERIC_CHARS.match(w["text"]):
                    near = [f for k in range(int(w["top"]) - 1, int(w["top"]) + 2) for f in by_line.get(k, [])]
                    inside = [f for f in near if f["x0"] >= w["x0"] - 0.1 and f["x1"] <= w["x1"] + 0.1
                              and abs(f["top"] - w["top"]) < 1]
                    if "".join(f["text"] for f in sorted(inside, key=lambda f: f["x0"])) != w["text"]:
                        raise ValueError(f"page {len(out) + 1}: could not split {w['text']!r} into cells "
                                         f"(slanted text?); refusing to guess")
                    words += [Word(f["x0"], f["top"], f["x1"], f["bottom"], f["text"]) for f in inside]
                else:
                    words.append(Word(w["x0"], w["top"], w["x1"], w["bottom"], w["text"]))
            out.append(words)
    return out


def text_sha(pages: list[str]) -> str:
    return hashlib.sha256("\f".join(pages).encode()).hexdigest()[:16]


def load_chains(path: Path = CHAINS_FILE) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def sources_by_pdf(chains: dict) -> dict[str, list[tuple[str, dict]]]:
    """pdf filename -> [(chain_key, source), ...]; one PDF can feed several chains."""
    out: dict[str, list[tuple[str, dict]]] = {}
    for key, chain in chains.items():
        for source in chain["sources"]:
            out.setdefault(source["pdf"], []).append((key, source))
    return out


def manifest_row(pdf: Path, chains: dict) -> dict:
    pages = page_texts(pdf)
    sizes = [len("".join(p.split())) for p in pages]
    users = sources_by_pdf(chains).get(pdf.name, [])
    return {
        "file": pdf.name,
        "pages": len(pages),
        "chars": sum(sizes),
        "text_sha": text_sha(pages),
        "chains": " ".join(key for key, _ in users),
        "parser": " ".join(sorted({s["parser"] for _, s in users})) or "unassigned",
        "image_pages": " ".join(str(i) for i, n in enumerate(sizes, start=1) if n < IMAGE_PAGE_MAX_CHARS),
    }

import hashlib
import html
import re
import subprocess
from pathlib import Path
from typing import NamedTuple

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

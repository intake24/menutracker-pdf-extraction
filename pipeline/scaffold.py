"""Draft a `config/chains.yaml` entry for a PDF that is new or has been replaced by a newer issue.

Nothing here edits the config: `draft_entry` returns YAML text for a person (or an agent) to read, check and paste. Every draft has
`approved: false`. Three cases:
  1. the chain exists and one of its sources has a similar file name (the same document, a newer issue): that source's options are copied
     with the new file name; the layout is probably unchanged, so run it and read the flags;
  2. the chain exists but no source is similar (a new document of a known chain): a skeleton with `parser: TODO`;
  3. a new chain: a skeleton for the whole chain with `parser: TODO`.
For a skeleton the parsers that fit the layout features are listed as comments, with the reason. The choice is still a person's.
"""
import difflib
import re
from pathlib import Path

import yaml

from pipeline.coverage import numeric_lines
from pipeline.ingest import page_texts

MARKS = re.compile(r"[✓✔●○▲]")
SIMILAR = 0.8


def _core(name: str) -> str:
    """A file name without its extension, month names, digits and version marks: what stays when only the issue date changes."""
    stem = Path(name).stem.lower()
    stem = re.sub(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b|[v]\d+|\d+", " ", stem)
    return " ".join(re.sub(r"[^a-z]+", " ", stem).split())


def similar_name(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, _core(a), _core(b)).ratio() >= SIMILAR


def layout_features(pdf: Path) -> dict:
    """What the manifest knows about a PDF plus two cheap counts that hint at the layout: data-looking lines and printed marks."""
    pages = page_texts(pdf)
    chars = [len("".join(p.split())) for p in pages]
    lines = numeric_lines(pdf, 3)
    return {"pages": len(pages), "chars": sum(chars), "image_pages": sum(n < 50 for n in chars), "numeric_lines": sum(lines.values()),
            "marks": len(MARKS.findall("".join(pages)))}


def suggest_parsers(features: dict) -> list[tuple[str, str]]:
    """(parser, reason) pairs from the layout features. A hint, not a decision: open the pages and read `playbook-new-batches.md`."""
    out = []
    pages = max(features.get("pages", 1), 1)
    blank = features.get("image_pages", 0)
    if blank >= pages * 0.5 or features.get("chars", 0) == 0:
        why = f"{blank} of {pages} pages have no text layer" if features.get("chars", 0) else "no text layer"
        return [("vision_table", f"{why}: a flat table or a menu is read from the page image"),
                ("vision_products", f"{why}: product sheets with a variant table"),
                ("vision_pairs", f"{why}: an allergen matrix page and a nutrition page for the same products")]
    if features.get("marks", 0) >= 10:
        out += [("allergen_matrix", "printed marks (tick, circle, triangle) under allergen labels"),
                ("mark_table", "printed marks and Yes/No diet cells")]
    if features.get("numeric_lines", 0) >= 5 * pages:
        out += [("numeric_table", "many lines that are a name followed by figures"),
                ("guide_rows", "rows with figures and a summary column of allergens"),
                ("portion_tables", "nutrition tables under product titles")]
    return out or [("vision_table", "little structure in the text layer: a model read may be needed; check the text layer first")]


def _dump(obj: dict) -> str:
    return yaml.safe_dump(obj, sort_keys=False, width=140, allow_unicode=True, default_flow_style=False)


def _indent(text: str, n: int) -> str:
    return "".join(" " * n + line if line.strip() else line for line in text.splitlines(True))


def draft_entry(chains: dict, key: str, pdf: str, features: dict) -> str:
    """YAML text for the new source (existing chain) or the whole chain (new chain); see the module docstring for the three cases."""
    base = {"pdf": pdf, "parser": "TODO", "region": "UK", "category": "food", "approved": False}
    hints = "".join(f"      # candidate: {p}: {why}\n" for p, why in suggest_parsers(features))
    facts = f"    # {features.get('pages', '?')} pages, {features.get('chars', '?')} characters of text, {features.get('image_pages', '?')} pages without text\n"
    chain = chains.get(key)
    if chain:
        match = next((s for s in chain["sources"] if similar_name(s["pdf"], pdf)), None)
        if match:
            copy = {**match, "pdf": pdf, "approved": False}
            return (f"# {key}: add this source (it replaces the older one when the new issue supersedes it).\n"
                    f"# copied from {match['pdf']} with the new file name; the layout is probably unchanged: run it, read the flags and the page checks.\n"
                    f"# Also: golden/{Path(match['pdf']).stem}.csv holds hand-checked rows for the old file; copy it to golden/{Path(pdf).stem}.csv and check each row\n"
                    f"# against the new PDF before approving. Options of the old source that were shared by YAML anchors are written out in full here.\n"
                    + _indent(_dump([copy]), 4))
        return (f"# {key}: add this source. No existing source of the chain has a similar file name, so this is a new document of a known chain\n"
                f"# (the chain's other sources are {', '.join(s['pdf'] for s in chain['sources'])}).\n" + facts
                + _indent(_dump([base]), 4) + hints)
    name = key.split("_", 1)[1] if "_" in key else key
    return (f"{key}:\n  chain: {name}\n  sources:\n" + facts
            + _indent(_dump([base]), 4) + hints
            + "# The chain key (<id>_<Name>) comes from Menu Tracker's menutracker.ipynb. A source is not run until `approved: true`.\n")

import re

from pipeline.columns import load_columns

ALLERGENS = load_columns().allergens
CEREALS = {"wheat": "wheat", "rye": "rye", "barley": "barley", "oats": "oats", "oat": "oats",
           "spelt": "spelt", "kamut": "kamut", "khorasan": "kamut"}
SIMPLE = {"celery": "celery", "crustacean": "crustacean", "crustaceans": "crustacean",
          "egg": "egg", "eggs": "egg", "fish": "fish", "lupin": "lupin", "milk": "milk",
          "mollusc": "mollusc", "molluscs": "mollusc", "mustard": "mustard",
          "peanut": "peanut", "peanuts": "peanut", "sesame": "sesame", "soya": "soya", "soy": "soya",
          "sulphite": "sulphite", "sulphites": "sulphite", "sulphur": "sulphite", "sulphur dioxide": "sulphite",
          "sulphites / sulphur dioxide": "sulphite", "sulphur dioxide / sulphites": "sulphite"}
CEREAL_HEADS = {"cereals containing gluten", "other cereals containing", "gluten"}
NUT_HEADS = {"tree nuts", "nuts"}
NONE_PHRASES = {"", "no major allergens", "none"}


class UnknownAllergen(ValueError):
    pass


SPECIES = {"fish", "crustacean", "crustaceans", "mollusc", "molluscs"}


def _simple_keys(head: str) -> list[str]:
    """'Sulphites / Sulphur Dioxide' is one allergen written two ways; 'Celery Milk' (a lost comma) is two."""
    if head in SIMPLE:
        return [SIMPLE[head]]
    if "/" in head:
        return sorted({_lookup(SIMPLE, part.strip()) for part in head.split("/")})
    words = head.split()
    if len(words) > 1 and all(w in SIMPLE for w in words):
        return [SIMPLE[w] for w in words]
    return [_lookup(SIMPLE, head)]


def _lookup(table: dict[str, str], term: str) -> str:
    if term not in table:
        raise UnknownAllergen(f"unknown allergen term {term!r}")
    return table[term]


def _terms(text: str) -> list[tuple[str, list[str]]]:
    """'Cereals (Wheat, Oats), Egg' -> [('cereals', ['wheat', 'oats']), ('egg', [])]"""
    out = []
    text = text.strip().rstrip(":.").strip()   # "Gluten, Wheat, Milk:" is printed with a trailing colon
    consumed = 0
    for m in re.finditer(r"([^,(]+?)\s*(?:\(([^)]*)\))?\s*(?:,|$)", text):
        if text[consumed:m.start()].strip(" ,"):
            break   # the regex skipped something (e.g. an unclosed bracket)
        consumed = m.end()
        head = m.group(1).strip().lower()
        if head:
            subs = [s.strip().lower() for s in (m.group(2) or "").split(",") if s.strip()]
            out.append((head, subs))
    if text[consumed:].strip(" ,"):
        raise UnknownAllergen(f"cannot read allergen text {text!r}")
    return out


def parse_allergens(contains: str, may_contain: str, unlisted: str) -> dict[str, str]:
    """Map 'Contains: ...' / 'May Contain: ...' text to allergen cells.

    `unlisted` is what the source's key says an allergen it doesn't list means: "No" when the
    guide declares it covers every major allergen, "" (not stated) otherwise.
    """
    result: dict[str, str] = {}
    nuts: dict[str, list[str]] = {"Yes": [], "May contain": []}
    # "May contain" first so "Yes" overwrites it when an allergen appears in both.
    for text, level in ((may_contain, "May contain"), (contains, "Yes")):
        if text.strip().rstrip(":.").strip().lower() in NONE_PHRASES:
            continue
        for head, subs in _terms(text):
            if head in CEREAL_HEADS:
                keys = ["gluten"] + [_lookup(CEREALS, s) for s in subs]
            elif head in NUT_HEADS:
                keys = ["treeNuts"]
                nuts[level] += [s.title() for s in subs]
            elif head in CEREALS and subs in ([], ["gluten"]):   # "Wheat (Gluten)": the cereal and gluten
                keys = ["gluten", CEREALS[head]]
            elif head in CEREALS and subs == ["gluten free"]:     # "Oats (Gluten Free)": the cereal, not gluten
                keys = [CEREALS[head]]
            elif subs and head in SPECIES:                        # "Fish (Tuna)": which species is detail only
                keys = [SIMPLE[head]]
            elif subs:
                raise UnknownAllergen(f"unexpected detail {subs!r} after allergen {head!r}")
            else:
                keys = _simple_keys(head)
            for k in keys:
                result[k] = level
    parts = []
    if nuts["Yes"]:
        parts.append(", ".join(nuts["Yes"]))
    if nuts["May contain"]:
        parts.append("may: " + ", ".join(nuts["May contain"]))
    if parts:
        result["treeNutSource"] = "; ".join(parts)
    return {a: unlisted for a in ALLERGENS} | result

"""Small helpers to edit config/chains.yaml as text (keeps its comments and anchors), used for the monthly renames.

    python -c "import sys; sys.path.insert(0, 'tools'); from cfgedit import rename, drop; rename('OLD.pdf', 'NEW.pdf'); drop('GONE.pdf')"

rename(old, new, chain=None)  every `- pdf: OLD` becomes `- pdf: NEW` (restricted to one chain key if given)
drop(pdf)                     removes every source whose pdf is `pdf` (a source with no PDF this month; an unapproved source stops its whole chain, so delete it instead of parking it)
                              CAUTION: a YAML anchor (&name) defined inside a dropped source must be moved to a source that stays (Vue 2026-09), then check `yaml.safe_load`.
Run from the repository root. Always check the diff with `git diff config/chains.yaml`.
"""
import re

PATH = "config/chains.yaml"


def rename(old: str, new: str, chain: str | None = None) -> None:
    s = open(PATH).read()
    if chain:
        i = s.index("\n" + chain + ":") + 1
        m = re.search(r"\n\S", s[i:])
        j = i + m.start() if m else len(s)
        s = s[:i] + s[i:j].replace("- pdf: " + old, "- pdf: " + new) + s[j:]
    else:
        s = s.replace("- pdf: " + old, "- pdf: " + new)
    open(PATH, "w").write(s)


def drop(pdf: str) -> None:
    parts = re.split(r"(?m)^(?=    - pdf: )", open(PATH).read())
    out = []
    for part in parts:
        if part.startswith("    - pdf: " + pdf + "\n"):
            m = re.search(r"(?m)^\S", part)   # keep what follows the source (the next chain's header and comments)
            out.append(part[m.start():] if m else "")
        else:
            out.append(part)
    open(PATH, "w").write("".join(out))

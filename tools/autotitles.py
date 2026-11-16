"""Run a chain again and again, adding every "unrecognised text above the table header 'X'" to the `titles` list of the chain's numeric_table sources, until the run passes or stops with another error.

Usage: python tools/autotitles.py CHAIN_KEY [--furniture]

By default X is appended to every `titles: [...]` line of the chain (a one-line flow list; a source without a `titles:` line is left alone). With --furniture it is appended to the chain's `furniture: [...]` lines instead (a line that is page furniture, not a title). Review `git diff config/chains.yaml` afterwards: a title that is really a product name or a wrong section label should not stay. Never use it to silence an error you do not understand: read the page.
"""
import re
import subprocess
import sys

PATH = "config/chains.yaml"


def add(chain: str, word: str, field: str) -> bool:
    lines = open(PATH).read().split("\n")
    inside, changed = False, False
    item = "'" + word.replace("'", "''") + "'"
    for n, line in enumerate(lines):
        if re.match(r"^" + re.escape(chain) + r":", line):
            inside = True
            continue
        if inside and line and not line.startswith(" ") and not line.startswith("#"):
            break
        if inside and line.strip().startswith(field + ":") and line.rstrip().endswith("]") and item not in line:
            inner = line.strip()[len(field) + 3:-1]
            lines[n] = line[: line.index(field + ":")] + f"{field}: [" + (inner + ", " if inner.strip() else "") + item + "]"
            changed = True
    if changed:
        open(PATH, "w").write("\n".join(lines))
    return changed


def main() -> int:
    chain = sys.argv[1]
    field = "furniture" if "--furniture" in sys.argv else "titles"
    for _ in range(80):
        out = subprocess.run(["uv", "run", "python", "-m", "pipeline.cli", "run", "--chain", chain], capture_output=True, text=True)
        text = out.stdout + out.stderr
        m = re.search(r"unrecognised text above the table header '(.*)'; list it under", text)
        if not m:
            print(text.strip().split("\n")[-1][:240])
            return 0 if out.returncode == 0 else 1
        print("add", field, m.group(1))
        if not add(chain, m.group(1), field):
            print("no", field, "line to extend for", m.group(1))
            return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())

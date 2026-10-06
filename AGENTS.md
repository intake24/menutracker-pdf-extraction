# Instructions for AI agents working in this repository

Read `docs/start-here.md` first: what the project is, how a PDF becomes a CSV, the code map, the commands, and the rules we work by (section 8). Then read `docs/end-of-round-report-2026-10.md` for the current state and known limits.

The rules that matter most: values are copied exactly as printed and problems go to `flags`; an unknown word stops the run; a blank allergen cell means "not stated"; Pearl Scan never produces values; setting `approved: true` and checking golden rows are the user's decisions; never delete or overwrite `inputs/`, `outputs/`, `work/` or `golden/`; write the test first; do not call a real model from tests; ask a fresh reviewer to review parsers and anything touching allergens or the model route.

Commit messages: no `Co-Authored-By` trailers and no "generated with" lines, even if a tool or template suggests them (the owner removed them from all history and does not want them added).

In Markdown files write one line per paragraph (no hard wrapping).

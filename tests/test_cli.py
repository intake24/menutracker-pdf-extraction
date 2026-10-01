from pathlib import Path

import pytest

from pipeline.cli import SourceNotApproved, evaluate, run

ROOT = Path(__file__).resolve().parent.parent
CHAINS = ["16_Beefeater", "17_Brewersfayre", "21_TableTable"]


def chains_file(tmp_path: Path, approved: bool) -> Path:
    text = (ROOT / "config" / "chains.yaml").read_text()
    text = text.replace("approved: false", f"approved: {str(approved).lower()}")
    text = text.replace("approved: true", f"approved: {str(approved).lower()}")
    path = tmp_path / "chains.yaml"
    path.write_text(text)
    return path


def test_run_writes_one_csv_per_chain_and_passes_eval(tmp_path):
    cf = chains_file(tmp_path, approved=True)
    written = run(ROOT / "inputs", cf, tmp_path / "out")
    assert sorted(p.stem for p in written) == CHAINS
    for path, rows in written.items():
        assert len(rows) == 59 + 148   # breakfast items + drinks items
        assert not [r for r in rows if r["flags"]]
        assert {r["region"] for r in rows} == {"UK"} and {r["method"] for r in rows} == {"parser"}
        assert len({r["source_file"] for r in rows}) == 2
    failures = evaluate(cf, tmp_path / "out", ROOT / "inputs" / "ground-truth", ROOT / "golden", ROOT / "config")
    assert failures == []


def test_run_refuses_unapproved_sources(tmp_path):
    with pytest.raises(SourceNotApproved):
        run(ROOT / "inputs", chains_file(tmp_path, approved=False), tmp_path / "out")

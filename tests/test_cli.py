from pathlib import Path

import pytest

from pipeline.cli import SourceNotApproved, evaluate, run

ROOT = Path(__file__).resolve().parent.parent
ROWS = {"16_Beefeater": 207, "17_Brewersfayre": 207, "21_TableTable": 207, "52_FiveGuys": 54}   # breakfast+drinks / table


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
    assert {p.stem: len(rows) for p, rows in written.items()} == ROWS
    for path, rows in written.items():
        flagged = [r for r in rows if r["flags"]]
        if path.stem != "52_FiveGuys":
            assert not flagged
        assert {r["region"] for r in rows} == {"UK"} and {r["method"] for r in rows} == {"parser"}
    failures = evaluate(cf, tmp_path / "out", ROOT / "inputs" / "ground-truth", ROOT / "golden", ROOT / "config")
    assert failures == []


def test_chain_without_allergen_information_has_no_allergen_columns(tmp_path):
    written = run(ROOT / "inputs", chains_file(tmp_path, approved=True), tmp_path / "out", "52_FiveGuys")
    [(path, rows)] = written.items()
    header = path.read_text().splitlines()[0].split(",")
    assert "milk" not in header and "gluten" not in header
    assert "energykJ_Per 100g/ml" in header and "energykJ_Per Portion" in header
    assert {r["source_file"] for r in rows} == {"nutrition.pdf"}


def test_five_guys_flags_are_arithmetic_inconsistencies_in_the_source(tmp_path):
    """Pearl Scan agrees with every value, so these are faithful to the PDF; flagged, never changed."""
    written = run(ROOT / "inputs", chains_file(tmp_path, approved=True), tmp_path / "out", "52_FiveGuys")
    [(_, rows)] = written.items()
    flagged = {r["Product_Name"]: r["flags"] for r in rows if r["flags"]}
    assert sorted(flagged) == ["Banana", "Banana Little", "Green Peppers", "HP Brown Sauce", "Jalapeño Peppers",
                               "Lettuce", "Mango", "Peanut Butter", "Relish"]
    arithmetic = ("error: kJ/kcal", "error: saturates >", "error: sugars >", "warn: Atwater")
    assert all(f.startswith(arithmetic) for flags in flagged.values() for f in flags.split(" | "))
    lettuce = next(r for r in rows if r["Product_Name"] == "Lettuce")
    assert (lettuce["energykJ_Per 100g/ml"], lettuce["energykCal_Per 100g/ml"]) == ("58", "19")


def test_run_refuses_unapproved_sources(tmp_path):
    with pytest.raises(SourceNotApproved):
        run(ROOT / "inputs", chains_file(tmp_path, approved=False), tmp_path / "out")

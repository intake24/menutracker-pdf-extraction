from pathlib import Path

import pytest

from pipeline.cli import SourceNotApproved, evaluate, run

ROOT = Path(__file__).resolve().parent.parent
ROWS = {"11_PizzaExpress": 818, "16_Beefeater": 207, "17_Brewersfayre": 207, "21_TableTable": 207, "52_FiveGuys": 54}
SOURCE_FLAGS = ("error: kJ/kcal", "error: saturates >", "error: sugars >", "warn: Atwater", "error: duplicate")   # the PDFs print these


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
        if path.stem in ("11_PizzaExpress", "52_FiveGuys"):   # their PDFs contain figures that fail the checks
            assert all(f.startswith(SOURCE_FLAGS) for r in flagged for f in r["flags"].split(" | "))
        else:
            assert not flagged
        assert {r["method"] for r in rows} == {"parser"}
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
        run(ROOT / "inputs", chains_file(tmp_path, approved=False), tmp_path / "out", "16_Beefeater")


def test_two_chains_sharing_a_pdf_each_get_their_own_column_mapping(tmp_path):
    import yaml
    chains = yaml.safe_load((ROOT / "config" / "chains.yaml").read_text())
    five = chains["52_FiveGuys"]["sources"][0] | {"approved": True}
    reverse = dict(five, columns=list(reversed(five["columns"])))
    cf = tmp_path / "chains.yaml"
    cf.write_text(yaml.safe_dump({"52_FiveGuys": {"chain": "A", "sources": [five]},
                                  "99_Reversed": {"chain": "B", "sources": [reverse]}}))
    written = run(ROOT / "inputs", cf, tmp_path / "out")
    by_chain = {p.stem: {r["Product_Name"]: r for r in rows} for p, rows in written.items()}
    assert by_chain["52_FiveGuys"]["Bacon"]["energykJ_Per Portion"] == "323"
    assert by_chain["99_Reversed"]["Bacon"]["energykJ_Per Portion"] == "6.6"   # the last printed cell


def test_run_skips_unapproved_chains_with_a_notice_but_refuses_when_asked_for_one(tmp_path, capsys):
    import yaml
    chains = yaml.safe_load((ROOT / "config" / "chains.yaml").read_text())
    for key, chain in chains.items():   # whatever is committed, Five Guys is the only unapproved chain here
        for source in chain["sources"]:
            source["approved"] = key != "52_FiveGuys"
    cf = tmp_path / "chains.yaml"
    cf.write_text(yaml.safe_dump(chains))
    written = run(ROOT / "inputs", cf, tmp_path / "out")
    assert sorted(p.stem for p in written) == sorted(k for k in ROWS if k != "52_FiveGuys")
    assert "skipped 52_FiveGuys: not approved" in capsys.readouterr().err
    with pytest.raises(SourceNotApproved):
        run(ROOT / "inputs", cf, tmp_path / "out", "52_FiveGuys")
    assert evaluate(cf, tmp_path / "out", ROOT / "inputs" / "ground-truth", ROOT / "golden", ROOT / "config") == []


def test_pizza_express_merges_the_uk_and_northern_ireland_pdfs_and_keeps_regions_apart(tmp_path):
    written = run(ROOT / "inputs", chains_file(tmp_path, approved=True), tmp_path / "out", "11_PizzaExpress")
    [(path, rows)] = written.items()
    by_region = {region: [r for r in rows if r["region"] == region] for region in ("UK", "NI")}
    assert {k: len(v) for k, v in by_region.items()} == {"UK": 453, "NI": 365}
    assert {r["source_file"] for r in by_region["NI"]} == {"BEL-Nutritional-Menu---May-2025.ashx.pdf"}
    header = path.read_text().splitlines()[0].split(",")
    assert "milk" not in header and "energykJ_Per 100g/ml" in header
    dupes = [r for r in rows if "duplicate" in r["flags"]]   # the PDF lists Smoky BBQ Chicken twice, in each region
    assert sorted((r["region"], r["Product_Name"]) for r in dupes) == [("NI", "Smoky BBQ Chicken"), ("UK", "Smoky BBQ Chicken")]


def test_two_sources_on_one_pdf_with_different_parser_options_are_not_parsed_once(tmp_path):
    import yaml
    chains = yaml.safe_load((ROOT / "config" / "chains.yaml").read_text())
    pex = chains["11_PizzaExpress"]["sources"][0] | {"approved": True}
    cf = tmp_path / "chains.yaml"
    cf.write_text(yaml.safe_dump({"98_Cache": {"chain": "X", "sources": [pex, pex | {"wrapped_names": False}]}}))
    with pytest.raises(ValueError, match="text between rows"):
        run(ROOT / "inputs", cf, tmp_path / "out")


def test_eval_says_what_it_did_not_evaluate_and_strict_fails_on_it(tmp_path, capsys):
    cf = chains_file(tmp_path, approved=True)
    run(ROOT / "inputs", cf, tmp_path / "out", only="52_FiveGuys")
    empty = tmp_path / "empty"
    empty.mkdir()
    args = (cf, tmp_path / "out", empty, empty, ROOT / "config")
    assert evaluate(*args, only="52_FiveGuys") == []
    assert "52_FiveGuys nutrition: not evaluated" in capsys.readouterr().out
    failures = evaluate(*args, only="52_FiveGuys", strict=True)
    assert failures and all("not evaluated" in f for f in failures)

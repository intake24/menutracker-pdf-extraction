from pipeline.vision_check import diff_rows, summary


def row(name, size="", page=1, flags="", **cells):
    return {"Product_Name": name, "Size": size, "source_page": page, "flags": flags, "method": "llm", **cells}


def test_summary_counts_rows_flagged_rows_and_cells_missing_where_peers_have_them():
    rows = [row("A", fat="1", salt="0.1"), row("B", fat="2", flags="error: saturates > fat"), row("C", page=2, fat="3")]
    s = summary(rows)
    assert s[1] == {"rows": 2, "flagged": 1, "empty_cells": 1} and s[2] == {"rows": 1, "flagged": 0, "empty_cells": 0}


def test_diff_rows_reports_cells_and_missing_rows_and_pairs_repeated_names_in_order():
    first = [row("A", "L", fat="1"), row("A", "L", fat="2"), row("B", fat="5")]
    second = [row("A", "L", fat="1"), row("A", "L", fat="3"), row("C", fat="5")]
    assert diff_rows(first, second) == ["A L.fat: '2' vs '3'", "row only in the first read: B", "row only in the re-read: C"]
    assert diff_rows(first, first) == []


def test_reread_lists_cells_that_differ_between_the_cached_read_and_a_second_read(tmp_path, monkeypatch):
    from pipeline.cli import ROOT, reread
    from pipeline.llm import Budget
    from pipeline.parsers import vision_table as vt
    monkeypatch.setattr(vt, "WORK", tmp_path)
    monkeypatch.setattr(vt, "BUDGET", Budget())
    def runner(prompt, schema, add_dir):
        kj = "11" if "pages_reread" in prompt else "10"
        return {"is_error": False, "structured_output": {"rows": [{"name": "A", "kj": kj}]}, "total_cost_usd": 0.01}
    monkeypatch.setattr(vt, "RUNNER", runner)
    lines = reread(ROOT / "inputs", ROOT / "config" / "chains.yaml", "58_Vue", [1], 200, "ice-cream")
    assert lines == ["58_Vue m19968-nutritional-info-ice-cream page 1: A.energykJ_Per Portion: '10' vs '11'"]
    assert (tmp_path / "pages_reread").exists() and (tmp_path / "pages").exists()


def test_diff_rows_ignores_dash_style_in_the_variant_label():
    assert diff_rows([row("A", "Crust – XXL", fat="1")], [row("A", "Crust - XXL", fat="1")]) == []

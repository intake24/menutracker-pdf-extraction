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


def test_text_check_counts_the_figures_printed_in_the_text_layer_against_the_rows_the_model_read():
    import pytest

    from pipeline.llm import LlmError
    from pipeline.parsers.vision_table import check_text_figures
    spec = {"field": "kcal", "pattern": r"(\d+)\s?kcal", "ignore": ["2000"]}
    text = "Halloumi fries (485kcal) 7.50  Wings (515 kcal) 8.00  Adults need 2000kcal a day"
    ok = {"rows": [{"name": "A", "kcal": "485"}, {"name": "B", "kcal": "515"}]}
    check_text_figures(ok, text, spec, 1)
    with pytest.raises(LlmError, match="485"):
        check_text_figures({"rows": [{"name": "B", "kcal": "515"}]}, text, spec, 1)           # a dish the model left out
    with pytest.raises(LlmError, match="999"):
        check_text_figures({"rows": ok["rows"] + [{"name": "C", "kcal": "999"}]}, text, spec, 1)   # a figure the page does not print


def test_a_pdf_name_with_dots_still_gives_its_page_image(tmp_path, monkeypatch):
    from pathlib import Path

    from pipeline.llm import Budget
    from pipeline.parsers import vision_table as vt
    monkeypatch.setattr(vt, "WORK", tmp_path)
    monkeypatch.setattr(vt, "BUDGET", Budget())
    monkeypatch.setattr(vt, "RUNNER", lambda prompt, schema, add_dir: {"is_error": False, "structured_output": {"rows": [{"name": "A"}]}, "total_cost_usd": 0.0})
    pdf = Path(__file__).resolve().parent.parent / "inputs" / "04.25-BK-Core-Menu-PB2.pdf"
    assert vt.page_rows(pdf, {"fields": {}, "instructions": "x"}, 1)[0]["Product_Name"] == "A"
    assert (tmp_path / "pages" / "04.25-BK-Core-Menu-PB2-1.png").exists()


def test_text_check_also_compares_the_tags_printed_just_before_a_figure():
    import pytest

    from pipeline.llm import LlmError
    from pipeline.parsers.vision_table import check_text_figures
    spec = {"field": "kcal", "pattern": r"(\d+)\s?kcal", "tags": {"field": "diet", "pattern": r"((?:\b(?:VE|V|T|I)\b\s+)*)\((\d+)\s?kcal\)"}}
    text = "Buddha bowl, rice VE T (457kcal) 12.00   Fries, salt (366kcal) 3.00"
    check_text_figures({"rows": [{"kcal": "457", "diet": "VE T"}, {"kcal": "366", "diet": "V"}]}, text, spec, 1)   # no tag printed beside 366: not checked
    with pytest.raises(LlmError, match="VE I"):
        check_text_figures({"rows": [{"kcal": "457", "diet": "VE I"}, {"kcal": "366", "diet": ""}]}, text, spec, 1)


def test_text_check_tags_can_be_limited_to_the_tags_that_are_read():
    from pipeline.parsers.vision_table import check_text_figures
    spec = {"field": "kcal", "pattern": r"(\d+)\s?kcal", "tags": {"field": "diet", "pattern": r"((?:\b(?:VE|V|T|I)\b\s+)*)\((\d+)\s?kcal\)", "keep": "VE|V"}}
    check_text_figures({"rows": [{"kcal": "457", "diet": "VE"}]}, "Buddha bowl VE T (457kcal) 12.00", spec, 1)


def test_text_check_can_strip_commas_and_signs_before_comparing():
    from pipeline.parsers.vision_table import check_text_figures
    spec = {"field": "kcal", "pattern": r"(\d[\d,]*)\s?kcal(?!\s*per serve)", "strip": ","}
    text = "Platter (1,706kcal serves 2, 853kcal per serve)  Rump (816kcal)  Add sauce 1.79 (+39kcal)"
    check_text_figures({"rows": [{"kcal": "1706"}, {"kcal": "816"}, {"kcal": "39"}]}, text, spec, 1)


def test_text_check_ignores_a_figure_after_stripping_commas():
    from pipeline.parsers.vision_table import check_text_figures
    spec = {"field": "kcal", "pattern": r"(\d[\d,]*)\s?kcal", "strip": ",", "ignore": [1800]}
    check_text_figures({"rows": [{"kcal": "50"}]}, "Fruit (50kcal)  Children need around 1,800kcal a day", spec, 1)


def test_vision_table_reads_only_the_listed_pages():
    from pathlib import Path

    from pipeline.parsers import vision_table as vt
    pdf = Path(__file__).resolve().parent.parent / "inputs" / "cookhouse_and_pub_main_menu_priceless.pdf"
    assert vt.pages_of(pdf, {"pages": [2, "4-5"]}) == [2, 4, 5] and vt.pages_of(pdf, {}) == list(range(1, 9))


def test_text_check_can_ignore_a_figure_on_one_page_only_where_the_text_layer_holds_hidden_text():
    from pipeline.llm import LlmError
    from pipeline.parsers.vision_table import check_text_figures
    import pytest
    spec = {"field": "kcal", "pattern": r"(\d+)\s?kcal", "page_ignore": {"7": [142]}}
    check_text_figures({"rows": [{"kcal": "50"}]}, "A (50kcal) hidden fruit tea (142kcal)", spec, 7)
    with pytest.raises(LlmError, match="142"):
        check_text_figures({"rows": [{"kcal": "50"}]}, "A (50kcal) hidden fruit tea (142kcal)", spec, 8)


def test_reread_all_pages_logs_each_page_and_report_counts_them(tmp_path, monkeypatch):
    import csv

    from pipeline.cli import ROOT, reread, verification_report
    from pipeline.llm import Budget
    from pipeline.parsers import vision_table as vt
    monkeypatch.setattr(vt, "WORK", tmp_path)
    monkeypatch.setattr(vt, "BUDGET", Budget())
    monkeypatch.setattr(vt, "RUNNER", lambda prompt, schema, add_dir: {"is_error": False, "structured_output": {"rows": [{"name": "A", "kj": "11" if "pages_reread" in prompt else "10"}]}, "total_cost_usd": 0.0})
    log = tmp_path / "reread_log.csv"
    lines = reread(ROOT / "inputs", ROOT / "config" / "chains.yaml", "58_Vue", None, 200, "ice-cream", log=log)
    rows = list(csv.DictReader(log.open()))
    assert [(r["chain"], r["page"], r["dpi"], r["differences"]) for r in rows] == [("58_Vue", str(p), "200", "1") for p in (1, 2, 3)] and len(lines) == 3
    rep = verification_report(ROOT / "config" / "chains.yaml", ROOT / "outputs", ROOT / "inputs" / "ground-truth", ROOT / "golden", reread_log=log)
    vue = next(r for r in rep if r["source_file"].startswith("m19968"))
    assert (vue["reread_pages"], vue["reread_differences"]) == (3, 3)

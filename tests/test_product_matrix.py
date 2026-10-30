from pathlib import Path

import yaml

from pipeline.parsers.product_matrix import parse

ROOT = Path(__file__).resolve().parent.parent


def test_odeon_uk_pre_packed_matrix_gives_one_row_per_product_with_figures_from_their_columns():
    draft = next(s for s in yaml.safe_load((ROOT / "config" / "chains.yaml").read_text())["59_Odeon"]["sources"]
                 if s["parser"] == "product_matrix" and s["region"] == "UK")
    rows = parse(ROOT / "inputs" / draft["pdf"], draft)
    assert len(rows) == 106
    first = rows[0]
    assert first["Product_Name"] == "Butterkist Crunchy Toffee Coated Popcorn 14 x 170g" and first["Category"] == "PRE PACKED POPCORN"
    assert (first["energykCal_Per 100g/ml"], first["Serving_Size"], first["Serving_Size_Unit"], first["energykCal_Per Portion"]) == ("424", "30", "g", "127")
    assert first["Ingredients"].startswith("Sugar, Glucose Syrup, Popped Maize") and first["Pack_Size"] == "170g"
    assert not any(k in r["Product_Name"] for r in rows for k in ("BOTTLED", "IMPULSE", "HANG BAGS"))   # group labels are not names
    smart = next(r for r in rows if r["Product_Name"].startswith("Glaceau Smartwater STILL"))
    assert smart["energykCal_Per Portion"] == "-"   # a dash is kept as printed


def test_line_gap_option_splits_rows_printed_three_points_apart():
    from types import SimpleNamespace
    from pipeline.parsers.product_matrix import parse_page
    def word(text, x, top):
        return {"x0": x, "x1": x + 6 * len(text), "top": top, "bottom": top + 6, "text": text}
    rects = [{"x0": 0, "x1": 700, "top": t, "bottom": t + 1} for t in (50, 300)]
    page = SimpleNamespace(rects=rects, chars=[])
    words = [word("A", 40, 100), word("10", 380, 100), word("B", 40, 103), word("20", 380, 103)]
    source = {"text_columns": [{"column": "Product_Name", "x0": 38}, {"column": "Pack_Size", "x0": 112}],
              "numeric_columns": [{"column": "energykJ_Per 100g/ml", "x": 390}, {"column": "energykCal_Per 100g/ml", "x": 420}]}
    rows, _ = parse_page(page, words, {**source, "line_gap": 2}, 1, "")
    assert [(r["Product_Name"], r["energykJ_Per 100g/ml"]) for r in rows] == [("A", "10"), ("B", "20")]


def test_invalid_values_option_keeps_an_excel_error_as_printed():
    from types import SimpleNamespace
    from pipeline.parsers.product_matrix import parse_page
    def word(text, x, top):
        return {"x0": x, "x1": x + 6 * len(text), "top": top, "bottom": top + 6, "text": text}
    page = SimpleNamespace(rects=[{"x0": 0, "x1": 700, "top": t, "bottom": t + 1} for t in (50, 300)], chars=[])
    words = [word("A", 40, 100), word("10", 380, 100), word("#VALUE!", 410, 100)]
    source = {"text_columns": [{"column": "Product_Name", "x0": 38}, {"column": "Pack_Size", "x0": 112}],
              "numeric_columns": [{"column": "energykJ_Per 100g/ml", "x": 390}, {"column": "energykCal_Per 100g/ml", "x": 420}]}
    rows, _ = parse_page(page, words, {**source, "invalid_values": ["#VALUE!"]}, 1, "")
    assert rows[0]["energykCal_Per 100g/ml"] == "#VALUE!"

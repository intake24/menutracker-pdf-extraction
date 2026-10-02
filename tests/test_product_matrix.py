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

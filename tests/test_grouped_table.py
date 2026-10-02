from pathlib import Path

import yaml

from pipeline.parsers.grouped_table import parse

ROOT = Path(__file__).resolve().parent.parent


def test_domino_pizza_labels_are_assigned_to_rows_by_position_and_size_order():
    draft = next(s for s in yaml.safe_load((ROOT / "config" / "chains.yaml").read_text())["6_Dominos"]["sources"]
                 if s["parser"] == "grouped_table" and s["pages"] == ["3-13"])
    draft = {**draft, "pages": [3]}
    rows = parse(ROOT / "inputs" / draft["pdf"], draft)
    first = [(r["Product_Name"], r["Crust"], r["Size"]) for r in rows[:6]]
    assert first == [("American Hot", "Classic Crust", "Large"), ("American Hot", "Classic Crust", "Medium"),
                     ("American Hot", "Classic Crust", "Small"), ("American Hot", "Classic Crust", "Personal"),
                     ("American Hot", "Italian Style Crust", "Large"), ("American Hot", "Italian Style Crust", "Medium")]
    assert rows[0]["energykCal_Per 100g/ml"] == "271" and rows[0]["energykCal_Per Slice"] == "233"


def test_domino_toppings_copy_the_per_100g_row_onto_each_size_row():
    src = next(s for s in yaml.safe_load((ROOT / "config" / "chains.yaml").read_text())["6_Dominos"]["sources"]
               if s["parser"] == "grouped_table" and s.get("shared_row"))
    rows = parse(ROOT / "inputs" / src["pdf"], {**src, "pages": [16]})
    pepperoni = [r for r in rows if r["Product_Name"] == "Pepperoni"]
    assert [r["Size"] for r in pepperoni] == ["Large", "Medium", "Small", "Personal"]
    assert {r["energykCal_Per 100g/ml"] for r in pepperoni} == {"467"} and pepperoni[0]["energykCal_Per Portion"] == "350"

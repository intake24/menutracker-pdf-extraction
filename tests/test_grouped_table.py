from pathlib import Path

import yaml

from pipeline.parsers.grouped_table import parse

ROOT = Path(__file__).resolve().parent.parent


def test_domino_pizza_labels_are_assigned_to_rows_by_position_and_size_order():
    draft = yaml.safe_load((ROOT / "docs" / "dominos-pizzas-config-draft.yaml").read_text())["6_Dominos_extra_sources"][0]
    draft = {**draft, "pages": [3]}
    rows = parse(ROOT / "inputs" / draft["pdf"], draft)
    first = [(r["Product_Name"], r["Crust"], r["Size"]) for r in rows[:6]]
    assert first == [("American Hot", "Classic Crust", "Large"), ("American Hot", "Classic Crust", "Medium"),
                     ("American Hot", "Classic Crust", "Small"), ("American Hot", "Classic Crust", "Personal"),
                     ("American Hot", "Italian Style Crust", "Large"), ("American Hot", "Italian Style Crust", "Medium")]
    assert rows[0]["energykCal_Per 100g/ml"] == "271" and rows[0]["energykCal_Per Slice"] == "233"

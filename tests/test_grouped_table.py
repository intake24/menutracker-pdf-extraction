from pathlib import Path

import pytest
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


def test_boswell_drinks_names_beside_the_middle_row_cans_with_a_serving_and_single_rows():
    src = next(s for s in yaml.safe_load((ROOT / "config" / "chains.yaml").read_text())["44_Boswell"]["sources"]
               if s["parser"] == "grouped_table")
    rows = parse(ROOT / "inputs" / src["pdf"], src)
    assert len(rows) == 110
    by = {(r["Product_Name"], r["Size"]): r for r in rows}
    assert by[("Cappuccino - Skimmed Milk", "Small")]["energykCal_Per Portion"] == "43"          # name printed beside the Regular row
    assert by[("Caffe Latte - Coconut", "Large")]["source_page"] == 2                            # continued from the page before, named beside the column titles
    assert [r["Size"] for r in rows if r["Product_Name"] == "Caffe Mocha - Skimmed Milk"] == ["Regular", "Large"]
    assert by[("Pepsi", "320")]["Serving_Size"] == "320" and by[("Pepsi", "320")]["Serving_Size_Unit"] == "g"
    assert by[("Kids Chocolate Flavoured Milk", "")]["energykCal_Per Portion"] == "136"


def _dominos_pizzas():
    return next(s for s in yaml.safe_load((ROOT / "config" / "chains.yaml").read_text())["6_Dominos"]["sources"]
                if s["parser"] == "grouped_table" and s["pages"] == ["3-17"])


def test_domino_cheese_label_covers_five_crusts_even_when_they_have_different_numbers_of_sizes():
    rows = parse(ROOT / "inputs" / "nutrition_pizzas.pdf", {**_dominos_pizzas(), "pages": [3]})
    first = [r for r in rows if r["Product_Name"] == "American Hot"]
    assert sum(r["Cheese"] == "Standard Mozzarella" for r in first) == 14 and sum(r["Cheese"] == "Reduced Fat Mozzarella" for r in first) == 14
    assert [r["Size"] for r in first if r["Crust"] == "Thin & Crispy Crust"][:3] == ["Large", "Medium", "Personal"]


def test_domino_pizza_continued_on_the_next_page_keeps_its_name():
    rows = parse(ROOT / "inputs" / "nutrition_pizzas.pdf", {**_dominos_pizzas(), "pages": [14, 15]})
    last = [r for r in rows if r["source_page"] == 15]
    assert len(last) == 1 and last[0]["Product_Name"] == "Tuna Supreme" and last[0]["Cheese"] == "Reduced Fat Mozzarella" and last[0]["Crust"] == "Thin & Crispy Crust"


def test_a_name_beside_the_middle_row_fills_only_the_one_unnamed_row_above_it():
    from pipeline.parsers.vision_products import rows_from_answer
    names = lambda ns: {"rows": [{"name": n, "variant": "Large", "values": {}} for n in ns]}
    src = {"header_columns": {}, "name_beside_middle_row": True, "variant_columns": False}
    got = [r["Product_Name"] for r in rows_from_answer(names(["", "Delight A", "Delight A", "", "Delight B", "Delight B"]), src, 2)]
    assert got == ["Delight A", "Delight A", "Delight A", "Delight B", "Delight B", "Delight B"]


def test_a_data_line_with_a_dash_cell_stops_the_run_instead_of_being_skipped(monkeypatch):
    """Boswells: 8 figure columns. A cell printed "-" leaves 7 numbers; the line used to fall under the data-line threshold and its row vanished without an error."""
    import dataclasses

    from pipeline.parsers import grouped_table as gt
    src = next(s for s in yaml.safe_load((ROOT / "config" / "chains.yaml").read_text())["44_Boswell"]["sources"] if s["parser"] == "grouped_table")
    real = gt.page_words_fine

    def with_dash(pdf, **kw):
        pages = real(pdf, **kw)
        for line in gt._lines(pages[0]):
            nums = [w for w in line if gt.NUMBER.match(w.text)]
            if len(nums) == 8:
                i = pages[0].index(nums[-1])
                pages[0][i] = dataclasses.replace(nums[-1], text="-") if dataclasses.is_dataclass(nums[-1]) else nums[-1]._replace(text="-")
                break
        return pages
    monkeypatch.setattr(gt, "page_words_fine", with_dash)
    with pytest.raises(ValueError, match="dash|'-'|cell"):
        parse(ROOT / "inputs" / src["pdf"], src)

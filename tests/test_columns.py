import pytest
from pydantic import ValidationError

from pipeline.columns import build_row_model, load_columns


def test_dictionary_starts_with_costa_columns_in_order():
    cols = list(load_columns().types)
    assert cols[:6] == ["Product_Name", "Product_Description", "Size", "Milk", "CoffeeType", "Ingredients"]
    assert cols.index("energykJ_Per 100g/ml") < cols.index("energykJ_Per Portion") < cols.index("gluten")
    assert cols[-1] == "treeNutSource"
    assert load_columns().types["milk"] == "allergen"


@pytest.mark.parametrize("value", ["93", "0.41", "<0.1", "< 0.5", "Trace", "trace", "Negligible", "Tr"])
def test_nutrient_cells_accept_numbers_and_known_words(value):
    Row = build_row_model(load_columns())
    Row.model_validate({"Product_Name": "x", "fat_Per Portion": value})


@pytest.mark.parametrize("bad", [
    {"energykCal_Per Portion": "93"},              # missing Product_Name
    {"Product_Name": "x", "fat_Per Portion": "lots"},  # nutrient text not in the dictionary
    {"Product_Name": "x", "fat_Per Portion": "."},     # stray printing glitch is flagged, not guessed
    {"Product_Name": "x", "milk": "N"},            # allergen vocabulary is Yes / May contain / No
    {"Product_Name": "x", "Colour": "red"},        # column not in the dictionary
])
def test_row_model_rejects(bad):
    with pytest.raises(ValidationError):
        build_row_model(load_columns()).model_validate(bad)


def test_dictionary_has_the_count_and_suitability_columns_later_chains_need():
    types = load_columns().types
    for col in ["Serves", "Portion_Type", "Number_of_Slices", "Total_Slices", "Total_Weight",
                "Suitable_for_Vegetarian", "Suitable_for_Vegan", "Suitable_for_Coeliac"]:
        assert types[col] == "text"


def test_standard_headings_name_our_columns_and_agree_with_the_pearl_scan_mapping():
    import yaml

    from pipeline.columns import COLUMNS_FILE
    spec = yaml.safe_load(COLUMNS_FILE.read_text())
    ours = set(load_columns().types)
    mapping = yaml.safe_load((COLUMNS_FILE.parent.parent / "config" / "pearlscan_columns.yaml").read_text())
    for column, h in spec["standard_headings"].items():
        assert column in ours, column
        if h["standard"] != "menu_section":       # sections follow our own naming rules and are not compared
            assert mapping[h["standard"]] == column, (h["standard"], column)


def test_a_standard_heading_never_collides_with_another_column_name():
    from pipeline.columns import PROVENANCE, standard_headings
    standard = standard_headings()
    names = [standard.get(c, c) for c in [*load_columns().types, *PROVENANCE]]
    assert len(names) == len(set(names)), sorted({n for n in names if names.count(n) > 1})   # two columns would share one CSV heading
    assert len(set(standard.values())) == len(standard)

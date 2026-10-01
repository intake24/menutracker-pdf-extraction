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

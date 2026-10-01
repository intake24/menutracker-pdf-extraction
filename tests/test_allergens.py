import pytest

from pipeline.allergens import ALLERGENS, UnknownAllergen, parse_allergens


def test_contains_and_may_contain_with_subtypes():
    got = parse_allergens(
        "Cereals containing Gluten (Wheat), Egg, Milk",
        "Other Cereals containing (Barley, Oats, Rye), Soya, Tree Nuts (Almond, Hazelnut)",
        unlisted="No",
    )
    assert {k: v for k, v in got.items() if v != "No"} == {
        "gluten": "Yes", "wheat": "Yes", "egg": "Yes", "milk": "Yes",
        "barley": "May contain", "oats": "May contain", "rye": "May contain",
        "soya": "May contain", "treeNuts": "May contain", "treeNutSource": "may: Almond, Hazelnut",
    }
    assert got["celery"] == "No" and got["spelt"] == "No"


def test_yes_beats_may_contain():
    got = parse_allergens("Cereals containing Gluten (Oats)", "Other Cereals containing (Barley, Wheat)", "No")
    assert got["gluten"] == "Yes" and got["oats"] == "Yes" and got["wheat"] == "May contain"


def test_no_major_allergens_uses_the_source_key():
    assert set(parse_allergens("No major allergens", "No major allergens", "No").values()) == {"No"}
    assert set(parse_allergens("No major allergens", "No major allergens", "").values()) == {""}
    assert set(parse_allergens("", "", "No")) == set(ALLERGENS)


def test_tree_nut_sources_both_levels():
    got = parse_allergens("Tree Nuts (Hazelnut)", "Tree Nuts (Almond)", "No")
    assert got["treeNuts"] == "Yes" and got["treeNutSource"] == "Hazelnut; may: Almond"


@pytest.mark.parametrize("text", ["Lupine", "Cereals containing Gluten (Corn)", "Gluten Free"])
def test_unknown_term_raises(text):
    with pytest.raises(UnknownAllergen):
        parse_allergens(text, "", "No")

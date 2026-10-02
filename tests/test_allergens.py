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


@pytest.mark.parametrize("contains", ["Celery (", "Milk, Cereals containing Gluten (", "Soya (traces)", "Milk (per 100ml)"])
def test_text_that_does_not_parse_completely_raises(contains):
    with pytest.raises(UnknownAllergen):
        parse_allergens(contains, "", "No")


def test_cereals_named_on_their_own_and_none_are_understood():
    from pipeline.allergens import parse_allergens
    r = parse_allergens("Gluten, Wheat, Milk", "None", "No")
    assert (r["gluten"], r["wheat"], r["milk"], r["barley"]) == ("Yes", "Yes", "Yes", "No")
    assert parse_allergens("None", "Barley", "")["barley"] == "May contain"


def test_a_trailing_colon_or_full_stop_is_ignored():
    from pipeline.allergens import parse_allergens
    assert parse_allergens("Gluten, Wheat, Milk:", "None.", "No")["milk"] == "Yes"


def test_papa_johns_wordings():
    from pipeline.allergens import UnknownAllergen, parse_allergens
    r = parse_allergens("Gluten, Wheat, Soya, Mustard, Sulphites/Sulphur Dioxide, Milk", "None", "No")
    assert (r["sulphite"], r["mustard"], r["soya"]) == ("Yes", "Yes", "Yes")
    assert parse_allergens("Milk, Sulphur / Sulphur Dioxide", "None", "No")["sulphite"] == "Yes"
    assert parse_allergens("Fish (Tuna), Milk", "None", "No")["fish"] == "Yes"
    r = parse_allergens("Gluten, Wheat, Oats (Gluten Free)", "None", "No")
    assert (r["oats"], r["gluten"]) == ("Yes", "Yes")                      # gluten comes from the wheat entry
    assert parse_allergens("Oats (gluten free)", "None", "No")["gluten"] == "No"
    assert parse_allergens("Wheat (Gluten)", "Milk", "No")["milk"] == "May contain"
    assert parse_allergens("Gluten, Wheat, Soya, Celery Milk", "None", "No")["celery"] == "Yes"
    with __import__("pytest").raises(UnknownAllergen):
        parse_allergens("Gluten, Kryptonite", "None", "No")

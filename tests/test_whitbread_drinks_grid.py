from collections import Counter
from pathlib import Path

import pytest

from pipeline.allergens import UnknownAllergen
from pipeline.ingest import Word
from pipeline.parsers.whitbread_drinks_grid import parse, parse_pages

INPUTS = Path(__file__).resolve().parent.parent / "inputs"
MARKERS = {"Y": "Yes", "": "No"}


def grid_page(*lines: tuple[float, list[tuple[float, str]]]) -> list[Word]:
    """A synthetic grid page: header labels at fixed x, then (y, [(x, text), ...]) lines."""
    header = [Word(146, 100, 160, 150, "Description"), Word(252, 160, 260, 190, "Wheat"),
              Word(282, 160, 290, 190, "Rye"), Word(312, 160, 320, 190, "Barley"),
              Word(342, 160, 350, 190, "Oat"), Word(432, 160, 440, 190, "Milk"),
              Word(552, 160, 560, 190, "Sulphite")]
    body = [Word(x, y, x + 8 * len(t), y + 8, t) for y, words in lines for x, t in words]
    return header + body


@pytest.mark.parametrize("pdf, items, marks", [
    ("beefeater_ss25_drinks_menu_allergy_nutrition_v1.pdf", 148, 82),
    ("brewers_fayre_allergy_nutrition_ss25_drinks_menu.pdf", 148, 83),
])
def test_every_item_and_mark_parsed(pdf, items, marks):
    rows = parse(INPUTS / pdf, {"markers": MARKERS})
    assert len(rows) == items
    yes = Counter(k for r in rows for k, v in r.items() if v == "Yes" and k != "gluten")
    assert sum(yes.values()) == marks  # every printed "Y" lands in exactly one allergen cell


def test_marks_land_in_their_columns():
    rows = parse(INPUTS / "beefeater_ss25_drinks_menu_allergy_nutrition_v1.pdf", {"markers": MARKERS})
    wine = next(r for r in rows if r["Product_Name"] == "JAM SHED, CHARDONNAY")
    assert {k for k, v in wine.items() if v == "Yes"} == {"egg", "milk", "fish", "sulphite"}
    assert wine["Category"] == "WINES - WHITE" and wine["spelt"] == ""  # grid has no spelt column: not stated
    carling = next(r for r in rows if r["Product_Name"] == "CARLING")
    assert carling["gluten"] == "Yes" and carling["barley"] == "Yes" and carling["oats"] == "No"


def test_headings_nest_until_an_item_appears():
    page = grid_page((220, [(380, "SPIRITS")]), (230, [(410, "GIN")]), (240, [(61, "HENDRICK'S")]),
                     (250, [(407, "VODKA")]), (260, [(61, "ABSOLUT"), (555, "Y")]))
    gin, vodka = parse_pages([page], MARKERS)
    assert gin["Category"] == "SPIRITS - GIN" and vodka["Category"] == "VODKA"
    assert vodka["sulphite"] == "Yes" and vodka["milk"] == "No" and vodka["gluten"] == "No"


def test_see_label_section_is_not_stated_and_does_not_nest():
    page = grid_page((220, [(300, "MIXERS - SEE PACKAGING LABEL FOR ALLERGENS")]), (230, [(61, "TONIC")]),
                     (240, [(400, "DRAUGHT")]), (250, [(61, "LAGER")]))
    tonic, lager = parse_pages([page], MARKERS)
    assert tonic["milk"] == "" and tonic["gluten"] == ""   # the grid gives no information here
    assert lager["Category"] == "DRAUGHT" and lager["milk"] == "No"


def test_unknown_marker_raises():
    page = grid_page((220, [(400, "BEERS")]), (230, [(61, "ODD ALE"), (315, "P")]))
    with pytest.raises(UnknownAllergen, match="ODD ALE"):
        parse_pages([page], MARKERS)


def test_mark_outside_any_column_raises():
    page = grid_page((220, [(400, "BEERS")]), (230, [(61, "ODD ALE"), (500, "Y")]))
    with pytest.raises(ValueError, match="under no allergen column"):
        parse_pages([page], MARKERS)

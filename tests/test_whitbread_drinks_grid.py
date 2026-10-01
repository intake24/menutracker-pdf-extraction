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


def real_pages(pdf: str) -> list[list[Word]]:
    from pipeline.ingest import page_words
    return page_words(INPUTS / pdf)


def yes_cells(rows: list[dict]) -> int:
    return sum(v == "Yes" for r in rows for k, v in r.items() if k != "gluten")


def test_mark_drifted_between_columns_raises():
    pages = real_pages("beefeater_ss25_drinks_menu_allergy_nutrition_v1.pdf")
    drifted = [[w._replace(x0=w.x0 + 14, x1=w.x1 + 14) if w.text == "Y" and i >= 2 else w for w in page]
               for i, page in enumerate(pages)]
    with pytest.raises(ValueError, match="under no allergen column"):
        parse_pages(drifted, MARKERS)


@pytest.mark.parametrize("dy", [0.15, 0.35, 0.55, 0.75])
def test_sub_point_vertical_offsets_keep_marks_on_their_line(dy):
    pages = real_pages("brewers_fayre_allergy_nutrition_ss25_drinks_menu.pdf")
    shifted = [[w._replace(y0=w.y0 + dy, y1=w.y1 + dy) for w in page] for page in pages]
    rows = parse_pages(shifted, MARKERS)
    assert len(rows) == 148 and yes_cells(rows) == 83
    assert "Y" not in {r["Category"] for r in rows}


def test_marker_only_line_raises():
    page = grid_page((220, [(400, "BEERS")]), (230, [(61, "ODD ALE")]), (240, [(555, "Y")]))
    with pytest.raises(ValueError, match="marker"):
        parse_pages([page], MARKERS)


def test_label_and_footer_words_in_the_body_do_not_drop_rows():
    pages = real_pages("beefeater_ss25_drinks_menu_allergy_nutrition_v1.pdf")
    # below the last item of page 5: a stray label word and a footer-like word
    pages[4] = pages[4] + [Word(757, 540, 766, 548, "Source"), Word(772, 545, 785, 551, "Page")]
    rows = parse_pages(pages, MARKERS)
    assert len(rows) == 148 and yes_cells(rows) == 82


def test_unrecognised_see_label_wording_raises():
    page = grid_page((220, [(300, "PACKAGED DRINKS - SEE PACKAGING FOR ALLERGEN INFORMATION")]), (230, [(61, "TONIC")]))
    with pytest.raises(ValueError, match="allergen heading"):
        parse_pages([page], MARKERS)

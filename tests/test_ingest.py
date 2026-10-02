import pytest
from pathlib import Path

from pipeline.ingest import load_chains, manifest_row, page_texts, page_words, page_words_fine, sources_by_pdf, text_sha

INPUTS = Path(__file__).resolve().parent.parent / "inputs"
BREAKFAST = [
    "beefeater_ss25_breakfast_menu_allergy_nutrition_v1.pdf",
    "brewers_fayre_allergy_nutrition_ss25_breakfast_menu.pdf",
    "table_table_allergy_nutrition_ss25_breakfast_menu.pdf",
]


def test_page_texts_one_per_page():
    assert len(page_texts(INPUTS / BREAKFAST[0])) == 7


def test_page_words_have_boxes_and_unescaped_text():
    pages = page_words(INPUTS / "beefeater_ss25_drinks_menu_allergy_nutrition_v1.pdf")
    assert len(pages) == 8
    words = [w for w in pages[2] if w.text == "&"]
    assert words and all(w.x1 > w.x0 and w.y1 > w.y0 for w in words)


def test_identical_pdfs_share_text_sha():
    assert len({text_sha(page_texts(INPUTS / f)) for f in BREAKFAST}) == 1


def test_one_pdf_per_source_and_six_chains_configured():
    chains = load_chains()
    assert set(chains) == {"11_PizzaExpress", "16_Beefeater", "17_Brewersfayre", "21_TableTable", "46_Cineworld", "52_FiveGuys"}
    assert all(len(users) == 1 for users in sources_by_pdf(chains).values())


def test_image_only_pages_reported():
    row = manifest_row(INPUTS / "nutritional-information.pdf", {})
    assert row["chains"] == "" and row["parser"] == "unassigned"
    assert len(row["image_pages"].split()) == 79


def test_fine_words_split_cells_that_poppler_returns_as_one_word():
    pdf = INPUTS / "PEX-Nutritional-Menu---May-2025.ashx.pdf"
    assert any(w.text == "123211.1" for w in page_words(pdf)[18])           # poppler: two cells, one word
    texts = [w.text for w in page_words_fine(pdf)[18]]
    assert "123211.1" not in texts and "1232" in texts and "11.1" in texts   # pdfplumber, by character gap


def test_fine_words_keep_ordinary_words_whole():
    texts = {w.text for w in page_words_fine(INPUTS / "PEX-Nutritional-Menu---May-2025.ashx.pdf")[10]}
    assert {"Goats", "Cheese", "Buddha", "Bowl"} <= texts


def test_fine_words_refuse_to_guess_when_the_pieces_do_not_rebuild_the_word():
    # Slanted text: the character pass groups characters across lines, so a number could silently become another.
    with pytest.raises(ValueError, match="could not split"):
        page_words_fine(INPUTS / "C_1-Core-Beverage-Allergen-Nutritional-Information-March-2025-Issued-28.03.25-3.pdf")

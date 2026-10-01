from pathlib import Path

from pipeline.ingest import load_chains, manifest_row, page_texts, page_words, sources_by_pdf, text_sha

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


def test_one_pdf_per_source_and_three_chains_configured():
    chains = load_chains()
    assert set(chains) == {"16_Beefeater", "17_Brewersfayre", "21_TableTable"}
    assert all(len(users) == 1 for users in sources_by_pdf(chains).values())


def test_image_only_pages_reported():
    row = manifest_row(INPUTS / "nutritional-information.pdf", {})
    assert row["chains"] == "" and row["parser"] == "unassigned"
    assert len(row["image_pages"].split()) == 79

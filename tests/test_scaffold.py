from pipeline.scaffold import draft_entry, similar_name, suggest_parsers

CHAINS = {"16_Beefeater": {"chain": "Beefeater", "sources": [
    {"pdf": "beefeater_ss25_drinks_menu_allergy_nutrition_v1.pdf", "parser": "whitbread_drinks_grid", "region": "UK", "category": "drinks",
     "approved": True, "markers": {"Y": "Yes", "": "No"}}]}}


def test_names_that_differ_only_in_dates_versions_and_digits_are_similar():
    assert similar_name("Pizza_Hut_Dietary_Booklet_March_2025.pdf", "Pizza_Hut_Dietary_Booklet_September_2025.pdf")
    assert similar_name("C1-Core-Food-May-2025-V47.pdf", "C1-Core-Food-Nov-2025-V48.pdf")
    assert not similar_name("nutrition.pdf", "brewers_fayre_allergy_menu.pdf")


def test_an_updated_pdf_of_an_existing_chain_copies_the_matching_source_unapproved():
    text = draft_entry(CHAINS, "16_Beefeater", "beefeater_ss26_drinks_menu_allergy_nutrition_v2.pdf", {"pages": 4, "image_pages": 0, "chars": 9000})
    assert "pdf: beefeater_ss26_drinks_menu_allergy_nutrition_v2.pdf" in text and "parser: whitbread_drinks_grid" in text and "approved: false" in text
    assert "markers" in text and "approved: true" not in text
    assert "copied from beefeater_ss25_drinks_menu_allergy_nutrition_v1.pdf" in text and "golden/beefeater_ss25_drinks_menu_allergy_nutrition_v1.csv" in text


def test_a_new_chain_gets_a_skeleton_with_no_parser_chosen_and_the_candidates_listed():
    text = draft_entry(CHAINS, "99_NewChain", "newchain_menu.pdf", {"pages": 10, "image_pages": 10, "chars": 0})
    assert text.startswith("99_NewChain:") and "chain: NewChain" in text and "parser: TODO" in text and "approved: false" in text
    assert "vision_table" in text and "no text layer" in text


def test_a_pdf_of_an_existing_chain_that_matches_no_source_is_a_new_source_skeleton():
    text = draft_entry(CHAINS, "16_Beefeater", "beefeater_kids_menu.pdf", {"pages": 2, "image_pages": 0, "chars": 3000})
    assert "parser: TODO" in text and "similar" in text and "16_Beefeater" in text


def test_parser_suggestions_follow_the_layout_features():
    assert suggest_parsers({"pages": 5, "image_pages": 5, "chars": 0, "numeric_lines": 0, "marks": 0})[0][0].startswith("vision_")
    assert any(p == "numeric_table" for p, _ in suggest_parsers({"pages": 3, "image_pages": 0, "chars": 9000, "numeric_lines": 90, "marks": 0}))
    assert any(p in ("allergen_matrix", "mark_table") for p, _ in suggest_parsers({"pages": 3, "image_pages": 0, "chars": 9000, "numeric_lines": 0, "marks": 40}))


def test_every_draft_is_valid_yaml_with_the_source_unapproved():
    import yaml
    for key, pdf, feats in (("16_Beefeater", "beefeater_ss26_drinks_menu_allergy_nutrition_v2.pdf", {"pages": 4, "image_pages": 0, "chars": 9000}),
                            ("16_Beefeater", "beefeater_kids.pdf", {"pages": 2, "image_pages": 0, "chars": 3000}),
                            ("99_NewChain", "new.pdf", {"pages": 3, "image_pages": 3, "chars": 0})):
        loaded = yaml.safe_load(draft_entry(CHAINS, key, pdf, feats))
        sources = loaded if isinstance(loaded, list) else loaded[key]["sources"] if key in loaded else loaded
        assert all(s["approved"] is False and s["pdf"] == pdf for s in sources), key


def test_a_pdf_where_most_pages_have_no_text_is_suggested_the_model_readers():
    out = suggest_parsers({"pages": 61, "image_pages": 45, "chars": 55000, "numeric_lines": 0, "marks": 0})
    assert [p for p, _ in out][:3] == ["vision_table", "vision_products", "vision_pairs"] and "45 of 61" in out[0][1]

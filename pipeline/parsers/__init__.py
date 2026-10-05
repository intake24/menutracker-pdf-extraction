from pipeline.parsers import allergen_matrix, grouped_table, numeric_table, product_matrix, vision_pairs, vision_products, vision_table, premier_inn_breakfast, whitbread_drinks_grid

# parser name (as used in config/chains.yaml) -> parse(pdf_path, source_config) -> rows
PARSERS = {
    "premier_inn_breakfast": premier_inn_breakfast.parse,
    "whitbread_drinks_grid": whitbread_drinks_grid.parse,
    "allergen_matrix": allergen_matrix.parse,
    "vision_table": vision_table.parse,
    "vision_products": vision_products.parse,
    "vision_pairs": vision_pairs.parse,
    "product_matrix": product_matrix.parse,
    "grouped_table": grouped_table.parse,
    "numeric_table": numeric_table.parse,
}

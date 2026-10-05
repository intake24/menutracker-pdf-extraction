from pipeline.parsers import allergen_matrix, drink_tables, guide_rows, grouped_table, mark_table, modifier_matrix, numeric_table, portion_tables, product_blocks, product_matrix, vision_pairs, vision_products, vision_table, premier_inn_breakfast, whitbread_drinks_grid

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
    "drink_tables": drink_tables.parse,
    "guide_rows": guide_rows.parse,
    "mark_table": mark_table.parse,
    "modifier_matrix": modifier_matrix.parse,
    "numeric_table": numeric_table.parse,
    "portion_tables": portion_tables.parse,
    "product_blocks": product_blocks.parse,
}

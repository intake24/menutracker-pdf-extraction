from pipeline.parsers import allergen_matrix, numeric_table, premier_inn_breakfast, whitbread_drinks_grid

# parser name (as used in config/chains.yaml) -> parse(pdf_path, source_config) -> rows
PARSERS = {
    "premier_inn_breakfast": premier_inn_breakfast.parse,
    "whitbread_drinks_grid": whitbread_drinks_grid.parse,
    "allergen_matrix": allergen_matrix.parse,
    "numeric_table": numeric_table.parse,
}

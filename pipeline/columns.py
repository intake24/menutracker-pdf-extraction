from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, create_model

COLUMNS_FILE = Path(__file__).resolve().parent.parent / "schemas" / "columns.yaml"
PROVENANCE = ["region", "source_file", "source_page", "method", "flags"]
ALLERGEN_VALUES = ("Yes", "May contain", "No")


@dataclass
class Columns:
    version: int
    types: dict[str, str]  # column -> "text" | "nutrient" | "allergen", in output order
    nutrient_words: list[str]
    bases: list[str]

    @property
    def allergens(self) -> list[str]:
        return [c for c, t in self.types.items() if t == "allergen"]


def load_columns(path: Path = COLUMNS_FILE) -> Columns:
    spec = yaml.safe_load(path.read_text())
    types = {c: "text" for c in spec["text_columns"]}
    for base in spec["bases"]:
        types |= {f"{n}_{base}": "nutrient" for n in spec["nutrients"]}
    types |= {a: "allergen" for a in spec["allergens"]}
    types |= {c: "text" for c in spec["trailing_text_columns"]}
    return Columns(spec["version"], types, spec["nutrient_words"], spec["bases"])


def nutrient_pattern(words: list[str]) -> str:
    return r"^(?:<\s?)?\d+(?:\.\d+)?$|^(?i:" + "|".join(words) + ")$"


def build_row_model(columns: Columns) -> type[BaseModel]:
    """Pydantic model keyed by CSV column name (aliases), rejecting unknown columns."""
    kinds = {
        "text": str,
        "nutrient": Annotated[str, StringConstraints(pattern=nutrient_pattern(columns.nutrient_words))],
        "allergen": Literal[ALLERGEN_VALUES],
    }
    fields = {"f0": (str, Field(alias="Product_Name"))}
    for i, (col, kind) in enumerate(columns.types.items(), start=1):
        if col != "Product_Name":
            fields[f"f{i}"] = (kinds[kind] | None, Field(default=None, alias=col))
    return create_model("Row", __config__=ConfigDict(extra="forbid"), **fields)

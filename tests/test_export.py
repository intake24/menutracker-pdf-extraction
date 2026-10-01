import csv

from pipeline.columns import PROVENANCE, load_columns
from pipeline.export import finalise, write_csv


def test_finalise_flags_without_changing_values_then_write(tmp_path):
    columns = load_columns()
    rows = [
        {"Product_Name": "Toast", "energykJ_Per Portion": "393", "energykCal_Per Portion": "93",
         "milk": "Yes", "egg": "No", "region": "UK", "source_page": 2},
        {"Product_Name": "Jam", "egg": "N", "fat_Per Portion": "1", "saturates_Per Portion": "2",
         "region": "UK", "source_page": 3, "flags": "error: no nutrition line found"},
    ]
    out = finalise(rows, columns)
    assert out[0]["flags"] == "" and out[0]["energykCal_Per Portion"] == "93"
    assert "no nutrition line found" in out[1]["flags"]
    assert "saturates > fat" in out[1]["flags"] and "egg" in out[1]["flags"]
    assert out[1]["egg"] == "N"   # invalid values are kept for the reviewer, never silently changed

    header = write_csv(out, columns, tmp_path / "16_Test.csv")
    assert header == ["Product_Name", "energykCal_Per Portion", "energykJ_Per Portion", "fat_Per Portion",
                      "saturates_Per Portion", "egg", "milk", *PROVENANCE]  # only columns with a value
    with (tmp_path / "16_Test.csv").open(newline="") as f:
        written = list(csv.DictReader(f))
    assert written[0]["egg"] == "No" and written[0]["source_page"] == "2" and written[1]["milk"] == ""

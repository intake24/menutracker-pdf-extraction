import json

import pytest

from pipeline.llm import Budget, BudgetExceeded, LlmError, RateLimited, call, claude_result

SCHEMA = {"type": "object", "properties": {"rows": {"type": "array"}}, "required": ["rows"]}
GOOD = {"is_error": False, "structured_output": {"rows": [{"name": "A"}]}, "total_cost_usd": 0.07,
        "usage": {"input_tokens": 4, "output_tokens": 100}}


class Fake:
    def __init__(self, *results):
        self.results, self.calls = list(results), 0

    def __call__(self, prompt, schema, add_dir):
        self.calls += 1
        return self.results.pop(0)


@pytest.fixture
def image(tmp_path):
    p = tmp_path / "pages" / "p1.png"
    p.parent.mkdir()
    p.write_bytes(b"png-bytes")
    return p


def test_a_call_returns_the_structured_rows_and_charges_the_budget(image, tmp_path):
    budget, fake = Budget(max_calls=5, max_usd=1.0), Fake(GOOD)
    out = call("read it", SCHEMA, image, runner=fake, cache_dir=tmp_path / "c", budget=budget)
    assert out == {"rows": [{"name": "A"}]} and (budget.calls, round(budget.usd, 2)) == (1, 0.07)


def test_an_unchanged_page_is_served_from_the_cache_without_a_call(image, tmp_path):
    fake, budget = Fake(GOOD, GOOD, GOOD), Budget()
    kw = dict(runner=fake, cache_dir=tmp_path / "c", budget=budget)
    call("read it", SCHEMA, image, **kw)
    call("read it", SCHEMA, image, **kw)
    assert fake.calls == 1 and budget.calls == 1
    call("read it differently", SCHEMA, image, **kw)   # a changed prompt is a new question
    assert fake.calls == 2
    image.write_bytes(b"other page")
    call("read it", SCHEMA, image, **kw)
    assert fake.calls == 3


def test_the_budget_stops_the_run_before_the_call_that_would_exceed_it(image, tmp_path):
    fake = Fake(GOOD, GOOD)
    budget = Budget(max_calls=1)
    call("one", SCHEMA, image, runner=fake, cache_dir=tmp_path / "c", budget=budget)
    with pytest.raises(BudgetExceeded):
        call("two", SCHEMA, image, runner=fake, cache_dir=tmp_path / "c", budget=budget)
    assert fake.calls == 1
    with pytest.raises(BudgetExceeded):   # cost cap
        call("three", SCHEMA, image, runner=Fake(GOOD), cache_dir=tmp_path / "c", budget=Budget(max_usd=0.05, usd=0.06))


def test_error_results_name_the_page_and_a_rate_limit_is_its_own_error(image, tmp_path):
    with pytest.raises(LlmError, match="p1.png.*boom"):
        call("x", SCHEMA, image, runner=Fake({"is_error": True, "result": "boom"}), cache_dir=tmp_path / "c", budget=Budget())
    with pytest.raises(RateLimited):
        call("x", SCHEMA, image, runner=Fake({"is_error": True, "result": "5-hour limit reached"}),
             cache_dir=tmp_path / "c", budget=Budget())
    with pytest.raises(LlmError, match="no structured output"):
        call("x", SCHEMA, image, runner=Fake({"is_error": False, "result": "chatty"}), cache_dir=tmp_path / "c", budget=Budget())
    assert not list((tmp_path / "c").glob("*.json"))   # failures are never cached


def test_claude_result_parses_stdout_and_reports_stderr_on_garbage():
    assert claude_result(json.dumps(GOOD), "", 0)["total_cost_usd"] == 0.07
    with pytest.raises(LlmError, match="exit 1.*bad news"):
        claude_result("", "bad news", 1)
    with pytest.raises(LlmError, match="not JSON"):
        claude_result("<html>", "", 0)


def test_vision_rows_are_mapped_to_dictionary_columns_with_the_portion_split_in_code(tmp_path, monkeypatch):
    from pipeline.parsers import vision_table as vt
    fields = {"kj": "energykJ_Per Portion", "kcal": "energykCal_Per Portion", "fat": "fat_Per Portion"}
    answer = {"rows": [
        {"section": "ICE CREAM", "name": "Vanilla", "size": "1 Scoop Tub", "portion": "85g", "kj": "82", "kcal": "197", "fat": "trace"},
        {"section": "TOPPINGS", "name": "Cone", "portion": "Per 1", "kj": "352", "kcal": "", "fat": "1.2"}]}
    rows = vt.rows_from_answer(answer, fields, 3)
    assert rows[0] == {"Product_Name": "Vanilla", "Category": "ICE CREAM", "source_page": 3, "method": "llm", "Size": "1 Scoop Tub",
                       "Serving_Size": "85", "Serving_Size_Unit": "g", "energykJ_Per Portion": "82",
                       "energykCal_Per Portion": "197", "fat_Per Portion": "trace"}
    assert rows[1]["Portion_Size"] == "Per 1" and "energykCal_Per Portion" not in rows[1]
    with pytest.raises(LlmError, match="without a name"):
        vt.rows_from_answer({"rows": [{"name": " ", "kj": "1"}]}, fields, 1)
    assert set(vt.schema_for(fields)["properties"]["rows"]["items"]["properties"]) == {"section", "name", "size", "portion", *fields}


def test_a_vision_source_parses_every_page_through_the_runner(tmp_path, monkeypatch):
    from pathlib import Path

    from pipeline.parsers import vision_table as vt
    monkeypatch.setattr(vt, "WORK", tmp_path)
    monkeypatch.setattr(vt, "BUDGET", Budget())
    seen = []

    def runner(prompt, schema, add_dir):
        seen.append((prompt, add_dir))
        return {"is_error": False, "structured_output": {"rows": [{"name": f"Item {len(seen)}", "kj": "1"}]}, "total_cost_usd": 0.01}
    monkeypatch.setattr(vt, "RUNNER", runner)
    pdf = Path(__file__).resolve().parent.parent / "inputs" / "m19968-nutritional-info-ice-cream.pdf"
    rows = vt.parse(pdf, {"fields": {"kj": "energykJ_Per Portion"}, "instructions": "A table."})
    assert [r["Product_Name"] for r in rows] == ["Item 1", "Item 2", "Item 3"] and {r["method"] for r in rows} == {"llm"}
    assert all("m19968-nutritional-info-ice-cream-" in p and p.count("Read the image") == 1 for p, _ in seen)
    assert seen[0][1] == tmp_path / "pages"

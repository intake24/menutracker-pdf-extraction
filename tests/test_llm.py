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


def test_an_answer_that_fails_validation_is_not_cached_so_a_fix_can_be_rerun(image, tmp_path):
    def must_have_rows(answer):
        if not answer["rows"]:
            raise LlmError("no rows")
    empty = {**GOOD, "structured_output": {"rows": []}}
    kw = dict(cache_dir=tmp_path / "c", budget=Budget(), validate=must_have_rows)
    with pytest.raises(LlmError, match="no rows"):
        call("x", SCHEMA, image, runner=Fake(empty), **kw)
    assert not list((tmp_path / "c").glob("*.json"))
    assert call("x", SCHEMA, image, runner=Fake(GOOD), **kw)["rows"]


def test_a_half_written_cache_file_is_a_miss_not_a_crash(image, tmp_path):
    kw = dict(cache_dir=tmp_path / "c", budget=Budget())
    call("x", SCHEMA, image, runner=Fake(GOOD), **kw)
    (next((tmp_path / "c").glob("*.json"))).write_text('{"rows": [{"na')
    fake = Fake(GOOD)
    assert call("x", SCHEMA, image, runner=fake, **kw)["rows"] and fake.calls == 1


def test_a_rate_limit_reported_only_on_stderr_is_still_a_rate_limit():
    with pytest.raises(RateLimited):
        claude_result("", "Claude usage limit reached. Your limit will reset at 3pm", 1)


def test_a_vision_page_with_no_rows_raises(tmp_path, monkeypatch):
    from pathlib import Path

    from pipeline.parsers import vision_table as vt
    monkeypatch.setattr(vt, "WORK", tmp_path)
    monkeypatch.setattr(vt, "BUDGET", Budget())
    monkeypatch.setattr(vt, "RUNNER", Fake({"is_error": False, "structured_output": {"rows": []}, "total_cost_usd": 0.01}))
    pdf = Path(__file__).resolve().parent.parent / "inputs" / "m19968-nutritional-info-ice-cream.pdf"
    with pytest.raises(LlmError, match="page 1.*no rows"):
        vt.parse(pdf, {"fields": {"kj": "energykJ_Per Portion"}, "instructions": "A table."})


def test_a_stopped_vision_chain_does_not_stop_the_other_chains(tmp_path, monkeypatch):
    import yaml

    from pipeline.cli import ROOT, run
    from pipeline.parsers import vision_table as vt
    monkeypatch.setattr(vt, "RUNNER", lambda *_: {"is_error": True, "result": "usage limit reached"})
    monkeypatch.setattr(vt, "WORK", tmp_path / "work")
    chains = yaml.safe_load((ROOT / "config" / "chains.yaml").read_text())
    chains = {k: chains[k] for k in ("58_Vue", "52_FiveGuys")}
    for chain in chains.values():
        for source in chain["sources"]:
            source["approved"] = True
    cf = tmp_path / "chains.yaml"
    cf.write_text(yaml.safe_dump(chains))
    stopped: list[str] = []
    written = run(ROOT / "inputs", cf, tmp_path / "out", stopped=stopped)
    assert [p.stem for p in written] == ["52_FiveGuys"]
    assert len(stopped) == 1 and stopped[0].startswith("58_Vue") and "usage limit" in stopped[0]


def test_a_cached_answer_that_fails_the_current_validation_is_asked_again(tmp_path):
    import pytest

    from pipeline.llm import Budget, LlmError, call
    img = tmp_path / "p.png"
    img.write_bytes(b"x")
    calls = []

    def runner(prompt, schema, add_dir):
        calls.append(1)
        return {"is_error": False, "structured_output": {"v": len(calls)}, "total_cost_usd": 0.0}

    def want_two(answer):
        if answer["v"] != 2:
            raise LlmError("not two")
    assert call("q", {}, img, cache_dir=tmp_path / "c", budget=Budget(), runner=runner)["v"] == 1       # cached without a check
    assert call("q", {}, img, cache_dir=tmp_path / "c", budget=Budget(), runner=runner, validate=want_two)["v"] == 2   # the check rejects it: asked again
    assert len(calls) == 2
    assert call("q", {}, img, cache_dir=tmp_path / "c", budget=Budget(), runner=runner, validate=want_two)["v"] == 2   # now cached and valid
    assert len(calls) == 2


# ---- backends: headless Claude Code or the Anthropic SDK, chosen by PIPELINE_LLM_BACKEND or --backend

class FakeMessages:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.sent = reply, error, None

    def create(self, **kwargs):
        self.sent = kwargs
        if self.error:
            raise self.error
        return self.reply


class FakeClient:
    def __init__(self, **kw):
        self.messages = FakeMessages(**kw)


def _reply(**over):
    from types import SimpleNamespace as NS
    base = dict(stop_reason="tool_use", content=[NS(type="tool_use", name="record_rows", input={"rows": [{"name": "A"}]})],
                usage=NS(input_tokens=4000, output_tokens=1500))
    return NS(**(base | over))


def test_the_sdk_runner_sends_the_image_and_a_forced_tool_and_returns_the_headless_result_shape(tmp_path):
    import base64

    from pipeline import llm
    img = tmp_path / "p.png"
    img.write_bytes(b"\x89PNGdata")
    client = FakeClient(reply=_reply())
    result = llm.sdk_runner("Read the image x.png. Return rows.", {"type": "object"}, tmp_path, image=img, client=client)
    sent = client.messages.sent
    assert result["structured_output"] == {"rows": [{"name": "A"}]} and result["is_error"] is False
    assert abs(result["total_cost_usd"] - (4000 * 2 + 1500 * 10) / 1e6) < 1e-9                    # Sonnet 5.5: $2 in, $10 out per million tokens
    assert sent["model"] == llm.MODEL and sent["tool_choice"] == {"type": "tool", "name": "record_rows"} and sent["tools"][0]["input_schema"] == {"type": "object"}
    blocks = sent["messages"][0]["content"]
    assert blocks[0]["type"] == "image" and blocks[0]["source"]["data"] == base64.b64encode(b"\x89PNGdata").decode()
    assert "Return rows." in blocks[1]["text"]


def test_the_sdk_runner_turns_a_cut_off_answer_a_rate_limit_and_a_missing_key_into_llm_errors(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS

    import anthropic
    import pytest

    from pipeline import llm
    img = tmp_path / "p.png"
    img.write_bytes(b"x")
    with pytest.raises(llm.LlmError, match="cut off"):
        llm.sdk_runner("q", {}, tmp_path, image=img, client=FakeClient(reply=_reply(stop_reason="max_tokens")))
    resp = NS(status_code=429, headers={}, request=NS(method="POST", url="https://api.anthropic.com"))
    with pytest.raises(llm.RateLimited):
        llm.sdk_runner("q", {}, tmp_path, image=img, client=FakeClient(error=anthropic.RateLimitError("slow down", response=resp, body=None)))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(llm.LlmError, match="ANTHROPIC_API_KEY"):
        llm.sdk_runner("q", {}, tmp_path, image=img)
    big = tmp_path / "big.png"
    big.write_bytes(b"x" * (llm.SDK_MAX_IMAGE_BYTES + 1))
    with pytest.raises(llm.LlmError, match="larger than"):
        llm.sdk_runner("q", {}, tmp_path, image=big, client=FakeClient(reply=_reply()))


def test_the_backend_is_chosen_at_call_time_and_an_unknown_name_is_refused(tmp_path, monkeypatch):
    import pytest

    from pipeline import llm
    seen = []
    monkeypatch.setattr(llm, "claude_runner", lambda prompt, schema, add_dir: seen.append("claude-code") or {})
    monkeypatch.setattr(llm, "sdk_runner", lambda prompt, schema, add_dir, image=None, client=None: seen.append("sdk") or {})
    for name in ("claude-code", "sdk"):
        monkeypatch.setattr(llm, "BACKEND", name)
        llm.runner("q", {}, tmp_path, image=tmp_path / "p.png")
    assert seen == ["claude-code", "sdk"]
    monkeypatch.setattr(llm, "BACKEND", "other")
    with pytest.raises(llm.LlmError, match="backend"):
        llm.runner("q", {}, tmp_path, image=tmp_path / "p.png")


def test_call_hands_the_image_to_a_runner_that_wants_it_and_not_to_the_others(tmp_path):
    from pipeline.llm import Budget, call
    img = tmp_path / "p.png"
    img.write_bytes(b"x")
    got = {}

    def wants(prompt, schema, add_dir, image=None):
        got["image"] = image
        return {"is_error": False, "structured_output": {"v": 1}, "total_cost_usd": 0.0}
    wants.wants_image = True
    call("q", {}, img, cache_dir=tmp_path / "c1", budget=Budget(), runner=wants)
    assert got["image"] == img
    call("q", {}, img, cache_dir=tmp_path / "c2", budget=Budget(), runner=lambda prompt, schema, add_dir: {"is_error": False, "structured_output": {"v": 1}, "total_cost_usd": 0.0})

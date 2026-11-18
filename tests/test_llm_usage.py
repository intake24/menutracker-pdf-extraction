import csv

import pytest

from pipeline import cli, llm
from pipeline.llm import Budget, call

SCHEMA = {"type": "object", "properties": {"rows": {"type": "array"}}, "required": ["rows"]}
GOOD = {"is_error": False, "structured_output": {"rows": []}, "total_cost_usd": 0.07, "usage": {"input_tokens": 4000, "output_tokens": 1500}}


@pytest.fixture
def image(tmp_path):
    p = tmp_path / "pages" / "Guide-7.png"
    p.parent.mkdir()
    p.write_bytes(b"png")
    return p


def test_every_real_call_is_logged_with_tokens_and_cost_and_a_cache_hit_is_not(image, tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "USAGE_LOG", tmp_path / "usage.csv")
    monkeypatch.setattr(llm, "BACKEND", "sdk")
    budget = Budget(max_calls=5, max_usd=1.0)
    for _ in range(2):   # the second call is served from the cache
        call("read it", SCHEMA, image, runner=lambda *a, **k: GOOD, cache_dir=tmp_path / "c", budget=budget)
    rows = list(csv.DictReader(open(tmp_path / "usage.csv")))
    assert len(rows) == 1 and (rows[0]["backend"], rows[0]["image"], rows[0]["input_tokens"], rows[0]["output_tokens"], rows[0]["cost_usd"]) == ("sdk", "Guide-7.png", "4000", "1500", "0.0700")
    assert (budget.input_tokens, budget.output_tokens) == (4000, 1500)


def test_the_api_backend_defaults_to_a_20_dollar_cap_headless_keeps_its_own_and_a_flag_overrides(monkeypatch):
    budget = Budget()
    monkeypatch.setattr(llm, "BUDGET", budget)
    llm.reset_budget("sdk")
    assert budget.max_usd == 20.0
    llm.reset_budget("claude-code")
    assert budget.max_usd == 60.0
    llm.reset_budget("sdk", max_usd=35.0)
    assert budget.max_usd == 35.0 and budget.usd == 0.0 and budget.calls == 0   # a new run starts from zero: that is the cap reset


def test_the_usage_summary_totals_tokens_and_cost_by_backend_and_by_pdf(tmp_path):
    log = tmp_path / "usage.csv"
    log.write_text("timestamp,backend,model,image,input_tokens,output_tokens,cost_usd\n"
                   "2026-11-16T10:00:00,sdk,claude-sonnet-5-5,Guide-7.png,4000,1500,0.023\n"
                   "2026-11-16T10:01:00,sdk,claude-sonnet-5-5,Guide-8.png,3000,2000,0.026\n"
                   "2026-11-16T10:02:00,claude-code,claude-sonnet-5-5,Other-1.png,,,0.05\n")
    text = cli.usage_summary(log)
    assert "| sdk | 2 | 7,000 | 3,500 | $0.05 |" in text and "| Guide | 2 | 7,000 | 3,500 | $0.05 |" in text
    assert "| claude-code | 1 |" in text and "$0.10" in text   # grand total


def test_the_interim_report_names_the_cap_the_spend_the_finished_chains_and_the_resume_command(tmp_path):
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "9_Subway.csv").write_text("Product_Name\nA\nB\n")
    budget = Budget(max_calls=400, max_usd=20.0, calls=80, usd=20.01)
    stopped = ["58_Vue: stopped: stopped before the next call: 80 calls and $20.01 used (caps 400 calls, $20.00); finished pages are cached, raise the cap and run again to resume"]
    text = cli.interim_report(stopped, out, budget, "sdk", tmp_path / "none.csv")
    assert "spend cap" in text and "$20.01" in text and "9_Subway" in text and "2 rows" in text and "58_Vue" in text
    assert "uv run python -m pipeline.cli --backend sdk run" in text and "--max-usd" in text


def test_the_interim_report_lists_only_the_chains_written_by_the_run_and_the_usage_table_folds_crops_into_their_pdf(tmp_path):
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "9_Subway.csv").write_text("Product_Name\nA\n")
    (out / "6_Dominos.csv").write_text("Product_Name\nA\nB\n")        # an older chain's CSV, not written by this run
    text = cli.interim_report(["x: stopped"], out, Budget(), "sdk", tmp_path / "none.csv", written=[out / "9_Subway.csv"])
    assert "9_Subway" in text and "6_Dominos" not in text
    log = tmp_path / "u.csv"
    log.write_text("timestamp,backend,model,image,input_tokens,output_tokens,cost_usd\n2026-11-17T10:00:00,sdk,m,nutrition_pizzas-2-crop3.png,1,1,0.1\n2026-11-17T10:00:01,sdk,m,nutrition_pizzas-5.png,1,1,0.1\n")
    assert "| nutrition_pizzas | 2 |" in cli.usage_summary(log)

"""Backend for pages the text layer can't be trusted on: one page image through headless Claude Code (`claude -p`).

`call` asks one question about one image, checks the answer against a JSON schema, and caches it under
work/llm/ keyed on the image, the prompt, the schema and the model, so a re-run over unchanged pages makes no call.
A run stops (never fails halfway silently) when it hits its call or cost cap, or the plan's usage limit; every page
already answered is cached, so the next run resumes where this one stopped.
"""
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

MODEL = "claude-sonnet-5-5"   # pinned by full id, never an alias: part of the cache key
PROMPT_VERSION = 1
TIMEOUT_S = 300
PER_CALL_USD = 0.5
RATE_LIMIT = re.compile(r"rate.?limit|usage limit|quota|limit reached|too many requests", re.I)


class LlmError(Exception):
    pass


class BudgetExceeded(LlmError):
    pass


class RateLimited(LlmError):
    pass


@dataclass
class Budget:
    """Caps for one run (defaults from the roadmap: 400 calls, $60)."""
    max_calls: int = 400
    max_usd: float = 60.0
    calls: int = 0
    usd: float = 0.0

    def check(self) -> None:
        if self.calls >= self.max_calls or self.usd >= self.max_usd:
            raise BudgetExceeded(f"stopped before the next call: {self.calls} calls and ${self.usd:.2f} used "
                                 f"(caps {self.max_calls} calls, ${self.max_usd:.2f}); finished pages are cached, "
                                 f"raise the cap and run again to resume")


def claude_result(stdout: str, stderr: str, code: int) -> dict:
    """The parsed `--output-format json` result of a `claude -p` run."""
    if not stdout.strip():
        raise LlmError(f"claude exit {code}, no output: {stderr[-300:]!r}")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        raise LlmError(f"claude exit {code}: output is not JSON: {stdout[:200]!r} {stderr[-200:]!r}") from None


def claude_runner(prompt: str, schema: dict, add_dir: Path) -> dict:
    """Run `claude -p` once. Tools are limited to Read; no session is kept; nothing secret is passed."""
    cmd = ["claude", "-p", "--model", MODEL, "--tools", "Read", "--add-dir", str(add_dir),
           "--max-budget-usd", str(PER_CALL_USD), "--no-session-persistence", "--output-format", "json",
           "--json-schema", json.dumps(schema), prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise LlmError(f"claude timed out after {TIMEOUT_S} s") from None
    return claude_result(r.stdout, r.stderr, r.returncode)


def _key(image: Path, prompt: str, schema: dict) -> str:
    h = hashlib.sha256(image.read_bytes())
    for part in (prompt, json.dumps(schema, sort_keys=True), MODEL, str(PROMPT_VERSION)):
        h.update(b"\0" + part.encode())
    return h.hexdigest()[:24]


def call(prompt: str, schema: dict, image: Path, *, cache_dir: Path, budget: Budget,
         runner: Callable[[str, dict, Path], dict] = claude_runner) -> dict:
    """The model's structured answer about `image`; the prompt must tell it to read the file at that path."""
    cached = cache_dir / f"{_key(image, prompt, schema)}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    budget.check()
    result = runner(prompt, schema, image.parent)
    budget.calls += 1
    budget.usd += result.get("total_cost_usd") or 0.0
    if result.get("is_error"):
        message = str(result.get("result"))[:300]
        raise (RateLimited if RATE_LIMIT.search(message) else LlmError)(f"{image.name}: {message}")
    answer = result.get("structured_output")
    if not isinstance(answer, dict):
        raise LlmError(f"{image.name}: no structured output in the answer: {str(result.get('result'))[:200]!r}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(answer))
    return answer

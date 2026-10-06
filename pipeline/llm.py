"""Backend for pages the text layer can't be trusted on: one page image through headless Claude Code (`claude -p`) or the Anthropic SDK.

Two backends give the same answers in the same shape and share one cache (the key does not name the backend, only the model):
  claude-code  headless `claude -p`, billed to the plan login (the default)
  sdk          the Anthropic Messages API, billed per token to ANTHROPIC_API_KEY; the page image is sent with the request
Choose with the environment variable PIPELINE_LLM_BACKEND or `python -m pipeline.cli --backend sdk <command>`.

`call` asks one question about one image, checks the answer against a JSON schema, and caches it under
work/llm/ keyed on the image, the prompt, the schema and the model, so a re-run over unchanged pages makes no call.
A run stops (never fails halfway silently) when it hits its call or cost cap, or the plan's usage limit; every page
already answered is cached, so the next run resumes where this one stopped.
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

MODEL = "claude-sonnet-5-5"   # pinned by full id, never an alias: part of the cache key
BACKENDS = ("claude-code", "sdk")
BACKEND = os.environ.get("PIPELINE_LLM_BACKEND", "claude-code")
RATES = {"claude-sonnet-5-5": (2.0, 10.0)}   # USD per million input and output tokens (Anthropic pricing page, 2026-10-06)
SDK_MAX_TOKENS = 16000                       # a full Papa John's page answer is about 9,000 tokens
SDK_MAX_IMAGE_BYTES = 5_000_000              # the API's limit per image
SDK_TIMEOUT_S = 300
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
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def check(self) -> None:
        if self.calls >= self.max_calls or self.usd >= self.max_usd:
            raise BudgetExceeded(f"stopped before the next call: {self.calls} calls and ${self.usd:.2f} used "
                                 f"(caps {self.max_calls} calls, ${self.max_usd:.2f}); finished pages are cached, "
                                 f"raise the cap and run again to resume")


def claude_result(stdout: str, stderr: str, code: int) -> dict:
    """The parsed `--output-format json` result of a `claude -p` run."""
    if not stdout.strip():
        raise (RateLimited if RATE_LIMIT.search(stderr) else LlmError)(f"claude exit {code}, no output: {stderr[-300:]!r}")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        raise LlmError(f"claude exit {code}: output is not JSON: {stdout[:200]!r} {stderr[-200:]!r}") from None


def claude_runner(prompt: str, schema: dict, add_dir: Path) -> dict:
    """Run `claude -p` once. Tools are limited to Read; no session is kept; nothing secret is passed."""
    cmd = ["claude", "-p", "--model", MODEL, "--tools", "Read", "--add-dir", str(add_dir),
           "--max-budget-usd", str(PER_CALL_USD), "--no-session-persistence", "--output-format", "json",
           "--setting-sources", "user", "--strict-mcp-config", "--disable-slash-commands",
           "--json-schema", json.dumps(schema), prompt]
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}   # bill the plan login, never a stray key
    try:   # run from an empty directory so no project settings or CLAUDE.md reach the model
        with tempfile.TemporaryDirectory() as cwd:
            r = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=TIMEOUT_S,
                               cwd=cwd, env=env)
    except subprocess.TimeoutExpired:
        raise LlmError(f"claude timed out after {TIMEOUT_S} s") from None
    return claude_result(r.stdout, r.stderr, r.returncode)


def sdk_runner(prompt: str, schema: dict, add_dir: Path, image: Path | None = None, client=None) -> dict:
    """One Messages API request: the page image, the instructions, and a forced tool whose input schema is the answer's JSON schema.

    Returns what `claude -p --output-format json` returns (structured_output, total_cost_usd, is_error) so `call` treats both alike."""
    import base64

    import anthropic
    if image is None:
        raise LlmError("the sdk backend needs the page image")
    if image.stat().st_size > SDK_MAX_IMAGE_BYTES:
        raise LlmError(f"{image.name}: the image is larger than {SDK_MAX_IMAGE_BYTES} bytes (lower the dpi)")
    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise LlmError("the sdk backend needs ANTHROPIC_API_KEY in the environment")
        client = anthropic.Anthropic(timeout=SDK_TIMEOUT_S)
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(image.read_bytes()).decode()}},
               {"type": "text", "text": "The page image is attached to this message; use it where the instructions name an image file.\n\n" + prompt}]
    try:
        reply = client.messages.create(model=MODEL, max_tokens=SDK_MAX_TOKENS, messages=[{"role": "user", "content": content}],
                                       tools=[{"name": "record_rows", "description": "Record the answer.", "input_schema": schema}],
                                       tool_choice={"type": "tool", "name": "record_rows"})
    except anthropic.RateLimitError as e:
        raise RateLimited(f"{image.name}: {e}") from None
    except anthropic.APIError as e:
        raise LlmError(f"{image.name}: {type(e).__name__}: {str(e)[:200]}") from None
    if reply.stop_reason == "max_tokens":
        raise LlmError(f"{image.name}: the answer was cut off at {SDK_MAX_TOKENS} tokens")
    answer = next((b.input for b in reply.content if b.type == "tool_use"), None)
    rate_in, rate_out = RATES[MODEL]
    cost = (reply.usage.input_tokens * rate_in + reply.usage.output_tokens * rate_out) / 1e6
    return {"is_error": False, "structured_output": answer, "total_cost_usd": cost}


sdk_runner.wants_image = True


def runner(prompt: str, schema: dict, add_dir: Path, image: Path | None = None) -> dict:
    """The backend chosen by `BACKEND`, looked up at call time so `--backend` and the environment variable both work."""
    if BACKEND == "claude-code":
        return claude_runner(prompt, schema, add_dir)
    if BACKEND == "sdk":
        return sdk_runner(prompt, schema, add_dir, image=image)
    raise LlmError(f"unknown backend {BACKEND!r}: use one of {BACKENDS}")


runner.wants_image = True


def _key(image: Path, prompt: str, schema: dict) -> str:
    h = hashlib.sha256(image.read_bytes())
    for part in (prompt, json.dumps(schema, sort_keys=True), MODEL, str(PROMPT_VERSION)):
        h.update(b"\0" + part.encode())
    return h.hexdigest()[:24]


def call(prompt: str, schema: dict, image: Path, *, cache_dir: Path, budget: Budget,
         runner: Callable[..., dict] = None,
         validate: Callable[[dict], None] = lambda answer: None) -> dict:
    """The model's structured answer about `image`; the prompt must tell it to read the file at that path.

    `validate` raises LlmError for an answer that can't be used; such an answer is never cached, and a cached one that fails it is asked again."""
    cached = cache_dir / f"{_key(image, prompt, schema)}.json"
    if cached.exists():
        try:
            answer = json.loads(cached.read_text())
            validate(answer)   # the checks may be stricter than when the answer was cached: a failing one is asked again
            return answer
        except (json.JSONDecodeError, LlmError):
            pass   # a write that was cut short, or an answer the current checks reject: ask again
    with budget.lock:
        budget.check()
        budget.calls += 1   # counted when started, so parallel calls cannot overshoot the cap
    runner = runner or globals()["runner"]
    result = runner(prompt, schema, image.parent, image=image) if getattr(runner, "wants_image", False) else runner(prompt, schema, image.parent)
    with budget.lock:
        budget.usd += result.get("total_cost_usd") or 0.0
    if result.get("is_error"):
        message = str(result.get("result"))[:300]
        raise (RateLimited if RATE_LIMIT.search(message) and result.get("subtype") != "error_max_budget_usd" else LlmError)(f"{image.name}: {message}")
    answer = result.get("structured_output")
    if not isinstance(answer, dict):
        raise LlmError(f"{image.name}: no structured output in the answer: {str(result.get('result'))[:200]!r}")
    try:
        validate(answer)
    except LlmError as e:
        raise LlmError(f"{image.name}: {e}") from None
    cache_dir.mkdir(parents=True, exist_ok=True)
    partial = cached.with_suffix(".tmp")
    partial.write_text(json.dumps(answer))
    os.replace(partial, cached)   # atomic: a killed run never leaves half a file
    return answer


BUDGET = Budget()   # the caps for one run: every parser that calls the model draws on this one

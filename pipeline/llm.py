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
DEFAULT_MAX_USD = {"claude-code": 60.0, "sdk": 20.0}   # the cap of one run; the API's is the owner's November 2026 choice: a re-run starts from zero (the cap reset)
USAGE_LOG = Path(__file__).resolve().parent.parent / "work" / "llm_usage.csv"   # one row per real call (never for a cache hit): the end-of-round report's token and cost summary reads it
WORKERS = {"claude-code": 3, "sdk": 8}   # pages read at once; the API has no plan window, headless stays at 3
PROMPT_VERSION = 1
TIMEOUT_S = 300
PER_CALL_USD = 0.5
RATE_LIMIT = re.compile(r"rate.?limit|usage limit|quota|limit reached|too many requests", re.I)


class LlmError(Exception):
    """`cost` and `usage` are set when the API answered (and billed) but the answer cannot be used."""
    cost: float = 0.0
    usage: dict = {}


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
    input_tokens: int = 0
    output_tokens: int = 0
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


def workers() -> int:
    return WORKERS[BACKEND]


def strict_schema(schema):
    """A copy of the JSON schema with `additionalProperties: false` on every object (the API's structured outputs require it)."""
    if isinstance(schema, list):
        return [strict_schema(x) for x in schema]
    if not isinstance(schema, dict):
        return schema
    out = {k: strict_schema(v) for k, v in schema.items()}
    if out.get("type") == "object" and "additionalProperties" not in out:   # a map that states its value schema stays as it is
        out["additionalProperties"] = False
    return out


def _free_form(schema) -> bool:
    """True when some object in the schema is a free-form map (additionalProperties states a schema): structured outputs cannot express it."""
    if isinstance(schema, list):
        return any(_free_form(x) for x in schema)
    if not isinstance(schema, dict):
        return False
    return isinstance(schema.get("additionalProperties"), dict) or any(_free_form(v) for v in schema.values())


def sdk_runner(prompt: str, schema: dict, add_dir: Path, image: Path | None = None, client=None) -> dict:
    """One Messages API request: the page image, the instructions, and a JSON-schema output format (structured outputs).

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
    plain = _free_form(schema)   # a free-form map cannot be expressed in structured outputs: ask for plain JSON and parse it (the parsers validate the answer)
    for attempt in (0, 1):
        body = content
        extra = {"output_config": {"format": {"type": "json_schema", "schema": strict_schema(schema)}}}   # Sonnet 5.5 rejects forced tool use (400): structured outputs, thinking off
        if plain:
            extra = {}
            body = [content[0], {**content[1], "text": content[1]["text"] + "\n\nReply with only one JSON object (no text before or after it) that matches this JSON schema:\n" + json.dumps(schema)}]
        try:
            reply = client.messages.create(model=MODEL, max_tokens=SDK_MAX_TOKENS, messages=[{"role": "user", "content": body}], thinking={"type": "between_tools"}, **extra)
            break
        except anthropic.RateLimitError as e:
            raise RateLimited(f"{image.name}: {e}") from None
        except anthropic.APIError as e:
            if not plain and attempt == 0 and ("too complex" in str(e) or "Grammar compilation" in str(e)):   # a schema too big for structured outputs: once more as plain JSON
                plain = True
                continue
            raise LlmError(f"{image.name}: {type(e).__name__}: {str(e)[:200]}") from None
    rate_in, rate_out = RATES[MODEL]
    cost = (reply.usage.input_tokens * rate_in + reply.usage.output_tokens * rate_out) / 1e6
    usage = {"input_tokens": reply.usage.input_tokens, "output_tokens": reply.usage.output_tokens}

    def billed(message: str) -> LlmError:   # an answer that failed was still billed: the caller adds it to the budget and the log
        err = LlmError(f"{image.name}: {message}")
        err.cost, err.usage = cost, usage
        return err
    if reply.stop_reason == "max_tokens":
        raise billed(f"the answer was cut off at {SDK_MAX_TOKENS} tokens")
    if reply.stop_reason == "refusal":
        raise billed("the model refused the page (stop_reason refusal)")
    text = next((b.text for b in reply.content if b.type == "text"), "")
    try:
        answer = json.loads(re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text))   # plain-JSON replies may come in a code fence
    except json.JSONDecodeError:
        raise billed(f"the answer is not JSON: {text[:200]!r}") from None
    if plain and (problem := _mismatch(answer, schema)):   # nothing enforced the schema: a wrong type would be cached and crash the parser on every re-run
        raise billed(f"the answer does not match the schema: {problem}")
    return {"is_error": False, "structured_output": answer, "total_cost_usd": cost, "usage": usage}


def _mismatch(value, schema, path: str = "answer") -> str:
    """The first place where `value` breaks the JSON schema (types, `required`, `properties`, `items`, a map's `additionalProperties`), else ''."""
    kind = schema.get("type")
    checks = {"object": dict, "array": list, "string": str, "boolean": bool}
    if kind in checks and not isinstance(value, checks[kind]) or kind in ("number", "integer") and (isinstance(value, bool) or not isinstance(value, (int, float))):
        return f"{path} is {type(value).__name__}, not {kind}"
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                return f"{path} has no {key!r}"
        extra = schema.get("additionalProperties")
        for key, item in value.items():
            sub = schema.get("properties", {}).get(key) or (extra if isinstance(extra, dict) else None)
            if sub and (found := _mismatch(item, sub, f"{path}.{key}")):
                return found
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(value):
            if found := _mismatch(item, schema["items"], f"{path}[{i}]"):
                return found
    return ""


sdk_runner.wants_image = True


def runner(prompt: str, schema: dict, add_dir: Path, image: Path | None = None) -> dict:
    """The backend chosen by `BACKEND`, looked up at call time so `--backend` and the environment variable both work."""
    if BACKEND == "claude-code":
        return claude_runner(prompt, schema, add_dir)
    if BACKEND == "sdk":
        return sdk_runner(prompt, schema, add_dir, image=image)
    raise LlmError(f"unknown backend {BACKEND!r}: use one of {BACKENDS}")


runner.wants_image = True


def _log_usage(image: Path, usage: dict, cost: float) -> None:
    """Append one row to USAGE_LOG (the caller holds the budget lock). A failed answer is logged too: it was billed."""
    import csv
    from datetime import datetime
    new = not USAGE_LOG.exists()
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with USAGE_LOG.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "backend", "model", "image", "input_tokens", "output_tokens", "cost_usd"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), BACKEND, MODEL, image.name, usage.get("input_tokens", ""), usage.get("output_tokens", ""), f"{cost:.4f}"])


def reset_budget(backend: str, max_usd: float | None = None) -> None:
    """Start a run: zero the counters of the shared BUDGET (parsers hold a reference to it, so it is changed in place) and set the cap
    to `max_usd`, else the backend's default (API $20, headless $60)."""
    BUDGET.calls, BUDGET.usd, BUDGET.input_tokens, BUDGET.output_tokens = 0, 0.0, 0, 0
    BUDGET.max_usd = max_usd if max_usd is not None else DEFAULT_MAX_USD[backend]


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
    try:
        result = runner(prompt, schema, image.parent, image=image) if getattr(runner, "wants_image", False) else runner(prompt, schema, image.parent)
    except LlmError as e:
        if e.cost or e.usage:   # the API billed an answer that could not be used
            with budget.lock:
                budget.usd += e.cost
                budget.input_tokens += e.usage.get("input_tokens") or 0
                budget.output_tokens += e.usage.get("output_tokens") or 0
                _log_usage(image, e.usage, e.cost)
        raise
    usage = result.get("usage") or {}
    with budget.lock:
        budget.usd += result.get("total_cost_usd") or 0.0
        budget.input_tokens += usage.get("input_tokens") or 0
        budget.output_tokens += usage.get("output_tokens") or 0
        _log_usage(image, usage, result.get("total_cost_usd") or 0.0)
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

# Estimate: token use and cost of the next batch on the Anthropic SDK (17 food chains, no Pearl Scan)

Written 2026-10-06. Scope: the model calls of an extraction round only (the pipeline's `llm.py` backend, today `claude -p`, moved to the Messages API). About 25 of the 35 PDFs are parsed from their text layer and cost nothing in tokens. New parser development and Opus reviews are not included: they depend on how different the next batch's layouts are.

## 1. Where the model is used (measured from this round)

| Source | Model calls |
|---|---|
| Papa John's (image pages) | 65 |
| Krispy Kreme (20 allergen and 21 nutrition pages) | 41 |
| Vue (3 PDFs) | 14 |
| Domino's page 2 (cropped bands) | 7 |
| Menus: Brewhouse 4, Cookhouse 9, Top Golf 10 | 23 |
| First read of 17 chains | about 150 |
| Second reads (`reread`) of allergen and flagged pages | about 40 |
| Retries when `text_check` rejects an answer (about 10%) | about 15 |
| **Total** | **about 205** (the cache holds 200 answers from this round) |

## 2. Tokens per call (measured)

Input about 4,000 tokens: the page image averages about 2,900 tokens (155 images measured by pixels ÷ 750; range 1,500 to 6,000 at 150 to 260 dpi) and the instructions plus schema about 1,000. Output about 1,500 tokens: the average cached answer is 4.2 KB of JSON; the largest (a full Papa John's page) is 30 KB, about 9,000 tokens.

Total for 205 calls: about **0.82 M input tokens** and **0.31 M output tokens**.

## 3. Rates (Anthropic pricing page, fetched 2026-10-06)

| Model | Input | Output | Batch input | Batch output | Cache read |
|---|---|---|---|---|---|
| Sonnet 5.5 (the model the pipeline pins) | $2 / MTok | $10 / MTok | $1 | $5 | $0.20 |
| Haiku 4.5 | $1 | $5 | $0.50 | $2.50 | $0.10 |
| Opus 5.5 | $4 | $20 | $2 | $10 | $0.20 |
| Fable 5.1 | $10 | $50 | $5 | $25 | $0.25 |

Other terms: the Batch API is 50% off input and output and stacks with caching; fast mode is not available with batch; a 5-minute cache write is 1.25 times the input price; forced tool use adds 286 tokens per call on Sonnet 5.5 (about $0.01 in total); US-only inference (`inference_geo: "us"`) adds 10%; models from 4.7 onward produce about 30% more text tokens than the old tokenizer. Source: https://platform.claude.com/docs/en/about-claude/pricing

## 4. Cost of one full round

| Model | Standard | Batch API |
|---|---|---|
| **Sonnet 5.5** | **about $4.7** | **about $2.4** |
| Sonnet 5.5, instructions cached | about $4.4 | about $2.2 |
| Haiku 4.5 | about $2.4 | about $1.2 |
| Opus 5.5 | about $9.5 | about $4.7 |
| Fable 5.1 | about $24 | about $12 |
| Today, `claude -p` (measured about $0.05 per call) | about $10 | not available |

Sonnet 5.5 standard: 0.82 M x $2 + 0.31 M x $10 = $1.64 + $3.10 = $4.74. Caching assumes about 900 of the roughly 1,000 text tokens per call are the repeated instructions, read at $0.20 instead of $2.

Range for Sonnet 5.5 standard: about $3 to $7. If output tokens run 30% above the estimate (new tokenizer), output is about 0.40 M tokens and the standard cost about $5.6; images are priced by pixels and are less affected.

Haiku 4.5 is the cheapest but small print is where a model misread 23% of Domino's figures, so it should be tested on those pages before use. Opus and Fable cost 2 to 5 times as much for transcription and are worth it only for pages that fail on Sonnet.

## 5. What drives the cost up

Image pages: about $0.035 per page on the standard API, so cost scales with the batch's page count. Resolution: 230 dpi or more for small print roughly doubles the image tokens of those pages. Second reads: with no Pearl Scan, every allergen page should be reread (20 to 40 more calls). Text layers: the more PDFs have one, the cheaper, and without one there is no `text_check` safety net.

## 6. Conclusions

A full extraction round on the SDK costs about $2 to $6 (under $3 on the Batch API), about half of today's headless cost, and it does not use up a plan quota (headless spends about 2 quota points per 5 calls). The cost that matters is agent time for new parsers and reviews, not the API calls.

The backend is now selectable (done 2026-10-06): `--backend sdk` or `PIPELINE_LLM_BACKEND=sdk` uses the Messages API (forced tool with the answer schema, page image attached, cost computed from the token usage at the rates above), `claude-code` stays the default, and both share one cache. It is tested with a fake client only; the first real use should compare one page with its cached headless answer. Instruction caching (section 4) is not implemented: the prompt starts with the page's image path, which would have to move to make the prefix cacheable. What the move needed was: `pipeline/llm.py` calls the Messages API with the page image and the JSON schema and keeps the same on-disk cache, validation and budget; pin the model version; read the key from `ANTHROPIC_API_KEY` (today it is stripped on purpose so a stray key is never billed); set a dollar cap per run. The cache key stays the same, and the SDK removes two cache-miss causes noted in the final review (user-level Claude settings loaded by `claude -p`, and the absolute image path in the prompt).

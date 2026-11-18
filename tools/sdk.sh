#!/bin/bash
# Run a pipeline command on the Anthropic API backend with the key read from the macOS Keychain (item `anthropic-api-key`, stored once with
# `security add-generic-password -U -a "$USER" -s anthropic-api-key -w` in a real terminal). The key exists only in this process.
# Usage: tools/sdk.sh run --chain 58_Vue      (= uv run python -m pipeline.cli --backend sdk run --chain 58_Vue; add --max-usd N before the command word if needed)
cd "$(dirname "$0")/.." || exit 1
ANTHROPIC_API_KEY="$(security find-generic-password -s anthropic-api-key -w)" exec uv run python -m pipeline.cli --backend sdk "$@"

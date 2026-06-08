#!/usr/bin/env bash
set -euo pipefail

SEED=""
PROB=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed) SEED="$2"; shift 2;;
    --prob) PROB="$2"; shift 2;;
    *) echo "Unknown arg: $1" >&2; exit 1;;
  esac
done

if [[ -z "$SEED" || -z "$PROB" ]]; then
  echo "Usage: $0 --seed <N> --prob <prob_v0.txt>" >&2
  exit 1
fi

MAX_BLOCK_DEPTH=2
MAX_BLOCK_SIZE=3
MAX_EXPR_COMPLEXITY=5


exec csmith \
  --seed "$SEED" \
  --probability-configuration "$PROB" \
  --max-block-depth "$MAX_BLOCK_DEPTH" \
  --max-block-size "$MAX_BLOCK_SIZE" \
  --max-expr-complexity "$MAX_EXPR_COMPLEXITY" \
  --no-safe-math \
  --max-funcs 1 \
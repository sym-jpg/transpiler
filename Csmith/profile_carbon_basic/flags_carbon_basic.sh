#!/usr/bin/env bash
set -euo pipefail

SEED=""
PROB=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed) SEED="$2"; shift 2;;
    --prob) PROB="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

if [[ -z "$SEED" || -z "$PROB" ]]; then
  echo "Usage: $0 --seed <N> --prob <prob_carbon_basic.txt>" >&2
  exit 2
fi

csmith \
  --seed "$SEED" \
  --probability-configuration "$PROB" \
  --max-block-depth 2 \
  --max-block-size 3 \
  --max-expr-complexity 4 \
  --no-safe-math \
  --max-funcs 1

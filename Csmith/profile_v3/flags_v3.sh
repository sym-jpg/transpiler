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
  echo "Usage: $0 --seed <N> --prob <prob.txt>" >&2
  exit 1
fi

exec csmith \
  --seed "$SEED" \
  --probability-configuration "$PROB" \
  --max-block-depth 4 \
  --max-block-size 6 \
  --max-expr-complexity 12 \
  --no-safe-math \
  --max-funcs 2


#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <source.cj> [output]" >&2
  exit 2
fi

SDK="${CJ_SYSROOT:-$(xcrun --sdk macosx --show-sdk-path)}"
SRC="$1"
OUT="${2:-/tmp/cjtest_run}"

cjc --sysroot "$SDK" --set-runtime-rpath "$SRC" -o "$OUT"
"$OUT"

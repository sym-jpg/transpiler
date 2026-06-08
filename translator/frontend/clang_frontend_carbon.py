from __future__ import annotations

import argparse
import sys
from pathlib import Path

from clang import cindex

from translator.backend.carbon_rules import DEFAULT_CARBON_RULES
from translator.backend.emitters import CarbonEmitter
from translator.frontend.clang_config import clang_parse_args, configure_libclang
from translator.frontend.clang_to_ir import lower_module
from translator.ir.type_normalization import normalize_module


configure_libclang()


def translate(filename: str, *, out_path: str | None = None) -> str:
    index = cindex.Index.create()
    tu = index.parse(
        filename,
        args=clang_parse_args(),
    )

    for diag in tu.diagnostics:
        print("[diag]", diag.severity, diag.spelling)

    module_ir = normalize_module(lower_module(tu.cursor))
    text = CarbonEmitter(DEFAULT_CARBON_RULES).emit_module(module_ir)

    if out_path:
        p = Path(out_path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    print(text)
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m translator.frontend.clang_frontend_carbon",
        description="Translate a core C file to Carbon using the basic Carbon emitter.",
    )
    parser.add_argument("input")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser()
    if not input_path.is_file():
        print(f"[clang_frontend_carbon] error: file not found: {input_path}", file=sys.stderr)
        return 2

    translate(str(input_path), out_path=args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

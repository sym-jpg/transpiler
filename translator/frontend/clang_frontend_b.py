from __future__ import annotations

import argparse
import sys
from pathlib import Path

from clang import cindex

from translator.backend.emitter_b import GeneratedCangjieEmitter
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

    from translator.backend.ruleset_autogen_b import AUTOGEN_RULES

    module_ir = normalize_module(lower_module(tu.cursor))
    text = GeneratedCangjieEmitter(AUTOGEN_RULES).emit_module(module_ir)

    if out_path:
        p = Path(out_path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    print(text)
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m translator.frontend.clang_frontend_b",
        description="Translate C IR using generated emitter B only.",
    )
    parser.add_argument("input")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser()
    if not input_path.is_file():
        print(f"[clang_frontend_b] error: file not found: {input_path}", file=sys.stderr)
        return 2

    translate(str(input_path), out_path=args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

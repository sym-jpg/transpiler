import argparse
import sys
from pathlib import Path

from clang import cindex
from clang.cindex import Cursor, CursorKind

from translator.frontend.clang_to_ir import lower_module
from translator.frontend.clang_config import clang_parse_args, configure_libclang
from translator.backend.carbon_rules import DEFAULT_CARBON_RULES
from translator.backend.emitters import CangjieEmitter
from translator.backend.ruleset import RuleMissing
from translator.autofix.types import Issue, IssueKind
from translator.autofix.patcher_ruleset import patch_autogen_ruleset

configure_libclang()


def dump_ast(filename: str, *, max_autofix_iters: int = 3, out_path: str | None = None):
    index = cindex.Index.create()
    tu = index.parse(
        filename,
        args=clang_parse_args(),
    )

    for d in tu.diagnostics:
        print("[diag]", d.severity, d.spelling)

    def visit(node, indent=0):
        print("  " * indent, node.kind, node.spelling, getattr(node.type, "spelling", ""))
        for c in node.get_children():
            visit(c, indent + 1)

    #visit(tu.cursor)

    def _issue_from_notimpl(e: Exception) -> Issue | None:
        msg = str(e)
        if msg.startswith("No expr rule for "):
            node = msg.removeprefix("No expr rule for ").strip()
            return Issue(kind=IssueKind.MISSING_EXPR_RULE, message=msg, node_type=node)
        if msg.startswith("No stmt rule for "):
            node = msg.removeprefix("No stmt rule for ").strip()
            return Issue(kind=IssueKind.MISSING_STMT_RULE, message=msg, node_type=node)
        return None

    def _make_emitter() -> CangjieEmitter:
        try:
            from translator.backend.ruleset_autogen import AUTOGEN_RULES

            rules = DEFAULT_CARBON_RULES.overlay(AUTOGEN_RULES)
        except Exception:
            rules = DEFAULT_CARBON_RULES
        return CangjieEmitter(rules=rules)

    def _maybe_write_module(module_text: str):
        if not out_path:
            return
        p = Path(out_path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(module_text, encoding="utf-8")

    emitter = _make_emitter()

    for it in range(max_autofix_iters + 1):
        try:
            module_ir = lower_module(tu.cursor)
            from translator.ir.type_normalization import normalize_module
            module_ir = normalize_module(module_ir)
            module_text = emitter.emit_module(module_ir)
            print(module_text)
            _maybe_write_module(module_text)
            return module_text
        except (NotImplementedError, RuleMissing) as e:
            issue = _issue_from_notimpl(e)
            if issue is None:
                raise
            print(f"[autofix] iter={it} kind={issue.kind} node={issue.node_type}")
            changed = patch_autogen_ruleset(issue)
            if not changed:
                print("[autofix] no change from patcher, stop")
                raise
            print("[autofix] patched ruleset_autogen.py, retry...")
            emitter = _make_emitter()

    raise RuntimeError("[autofix] reached max_autofix_iters")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m translator.frontend.clang_frontend",
        description="Dump clang AST and/or lower to IR for a given C file",
    )
    parser.add_argument(
        "input",
        help="Path to input C file, e.g. dataset/sample.c",
    )
    parser.add_argument(
        "--autofix-iters",
        type=int,
        default=3,
        help="Max autofix iterations per function (default: 3)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Write generated code to this file (e.g. out.cj). If omitted, only prints to stdout.",
    )

    args = parser.parse_args(argv)
    input_path = Path(args.input).expanduser()
    if not input_path.is_file():
        print(f"[clang_frontend] error: file not found: {input_path}", file=sys.stderr)
        return 2

    dump_ast(
        str(input_path),
        max_autofix_iters=int(args.autofix_iters),
        out_path=args.out,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

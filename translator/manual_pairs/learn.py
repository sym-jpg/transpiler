from __future__ import annotations

import argparse
import ast
import importlib
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from translator.autofix.llm_client import llm_chat_json
from translator.autofix.ruleset_autogen_writer import apply_patch
from translator.manual_pairs.eval import eval_pair
from translator.manual_pairs.pair_context import build_pair_prompt_context, load_pairs


Kind = Literal["expr", "stmt"]
Backend = Literal["a", "b"]


BACKEND_CONFIG = {
    "a": {
        "frontend": "a",
        "autogen_path": Path("translator/backend/ruleset_autogen.py"),
        "autogen_module": "translator.backend.ruleset_autogen",
    },
    "b": {
        "frontend": "b",
        "autogen_path": Path("translator/backend/ruleset_autogen_b.py"),
        "autogen_module": "translator.backend.ruleset_autogen_b",
    },
}


PROMPT_TEMPLATE = """You are generating Python emitter rules for a source-to-source transpiler.

Goal:
- The frontend has already lowered C code into a language-independent IR.
- Different target languages need different emitter rules.
- Generate one target-language emitter rule from manual C-to-{target_name} reference pairs.

Target language: {target_name}
Rule to generate:
- kind: {kind}
- IR node: {node}

Emitter API:
- ExprEmitter signature: (emitter, expr) -> str
- StmtEmitter signature: (emitter, stmt, indent) -> list[str]
- emitter.emit_expr(expr) -> str
- emitter.emit_type(ty) -> str
- emitter.emit_op(op) -> str
- emitter.emit_unary_op(op) -> str
- emitter.emit_block(block, indent) -> list[str]
- emitter.stmt_term: string, empty for Cangjie
- emitter.fresh_tmp() -> str

IR node definitions:
```python
{ir_nodes}
```

Rules:
- Generate exactly one Python function.
- Do not generate RuleSet, AUTOGEN_RULES, mapping dicts, imports, tests, markdown, or comments.
- Function name must start with "emit_".
- For expr rules, return a string.
- For stmt rules, return list[str] lines.
- For stmt rules, use pad = "  " * indent.
- Prefer deterministic direct emission.
- Match the reference pairs' target-language style.
- Preserve C-like semantics where the reference pairs show explicit helper calls or casts.
- Do not emit C syntax when the target language requires different syntax.
- Do not delegate to existing target-specific backend methods such as emitter.emit_assign_stmt, emitter.emit_vardecl_stmt, emitter.emit_while_stmt, emitter.emit_if_stmt, emitter.emit_index_assign, or default_init_expr.
- The generated function must be self-contained except for the generic emitter API and IR node classes already available in ruleset_autogen.py.

Output JSON only:
{{
  "kind": "{kind}",
  "node": "{node}",
  "func_name": "emit_...",
  "func_code": "def emit_...(emitter, ...):\\n    ..."
}}
"""


@dataclass(frozen=True)
class RuleSpec:
    kind: Kind
    node: str


@dataclass(frozen=True)
class BackendSpec:
    name: Backend
    frontend: str
    autogen_path: Path
    autogen_module: str


def resolve_backend(name: Backend) -> BackendSpec:
    config = BACKEND_CONFIG[name]
    return BackendSpec(
        name=name,
        frontend=str(config["frontend"]),
        autogen_path=Path(config["autogen_path"]).resolve(),
        autogen_module=str(config["autogen_module"]),
    )


@contextmanager
def autogen_backend_env(backend: BackendSpec):
    old_path = os.environ.get("AUTOGEN_RULESET_PATH")
    old_module = os.environ.get("AUTOGEN_RULESET_MODULE")
    os.environ["AUTOGEN_RULESET_PATH"] = str(backend.autogen_path)
    os.environ["AUTOGEN_RULESET_MODULE"] = backend.autogen_module
    try:
        yield
    finally:
        if old_path is None:
            os.environ.pop("AUTOGEN_RULESET_PATH", None)
        else:
            os.environ["AUTOGEN_RULESET_PATH"] = old_path
        if old_module is None:
            os.environ.pop("AUTOGEN_RULESET_MODULE", None)
        else:
            os.environ["AUTOGEN_RULESET_MODULE"] = old_module


def _load_ir_nodes_source(max_chars: int = 12000) -> str:
    path = Path("translator/ir/nodes.py")
    return path.read_text(encoding="utf-8", errors="replace")[:max_chars]


def _parse_rule_spec(text: str) -> RuleSpec:
    if ":" not in text:
        raise argparse.ArgumentTypeError("rule must use format expr:Node or stmt:Node")
    kind, node = text.split(":", 1)
    kind = kind.strip()
    node = node.strip()
    if kind not in ("expr", "stmt"):
        raise argparse.ArgumentTypeError("rule kind must be expr or stmt")
    if not node:
        raise argparse.ArgumentTypeError("rule node cannot be empty")
    return RuleSpec(kind=kind, node=node)


def _validate_func_code(func_name: str, func_code: str) -> None:
    tree = ast.parse(func_code)
    body = tree.body
    if len(body) != 1 or not isinstance(body[0], ast.FunctionDef):
        raise RuntimeError("LLM output must contain exactly one top-level function")
    fn = body[0]
    if fn.name != func_name:
        raise RuntimeError(f"func_name mismatch: JSON says {func_name}, code defines {fn.name}")
    if not func_name.startswith("emit_"):
        raise RuntimeError(f"invalid emitter function name: {func_name}")

    forbidden = (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)
    forbidden_emitter_attrs = {
        "emit_assign_stmt",
        "emit_vardecl_stmt",
        "emit_while_stmt",
        "emit_if_stmt",
        "emit_index_assign",
        "emit_condition",
        "declare_pointer",
        "assign_pointer",
        "resolve_deref_target",
    }
    forbidden_names = {"default_init_expr"}
    for node in ast.walk(tree):
        if isinstance(node, forbidden):
            raise RuntimeError(f"forbidden syntax in generated function: {type(node).__name__}")
        if isinstance(node, ast.Attribute) and node.attr in forbidden_emitter_attrs:
            raise RuntimeError(f"forbidden backend delegation in generated function: {node.attr}")
        if isinstance(node, ast.Name) and node.id in forbidden_names:
            raise RuntimeError(f"forbidden external helper in generated function: {node.id}")


def build_rule_prompt(
    spec: RuleSpec,
    *,
    target_name: str,
    pair_root: Path,
    features: list[str],
    max_pairs: int,
) -> dict:
    context = build_pair_prompt_context(pair_root, features, max_pairs=max_pairs)
    if not context:
        raise RuntimeError(f"no manual pairs found under {pair_root}")

    return (
        context
        + "\n\n"
        + PROMPT_TEMPLATE.format(
            target_name=target_name,
            kind=spec.kind,
            node=spec.node,
            ir_nodes=_load_ir_nodes_source(),
        )
    )


def _generate_rule(
    spec: RuleSpec,
    *,
    target_name: str,
    pair_root: Path,
    features: list[str],
    max_pairs: int,
) -> dict:
    prompt = build_rule_prompt(
        spec,
        target_name=target_name,
        pair_root=pair_root,
        features=features,
        max_pairs=max_pairs,
    )
    data = llm_chat_json(prompt)
    if data.get("kind") != spec.kind:
        raise RuntimeError(f"kind mismatch: expected {spec.kind}, got {data.get('kind')}")
    if data.get("node") != spec.node:
        raise RuntimeError(f"node mismatch: expected {spec.node}, got {data.get('node')}")
    func_name = str(data.get("func_name", ""))
    func_code = str(data.get("func_code", ""))
    _validate_func_code(func_name, func_code)
    return data


def _sanity_check_autogen(spec: RuleSpec) -> None:
    module_name = os.environ.get("AUTOGEN_RULESET_MODULE", "translator.backend.ruleset_autogen")
    m = importlib.import_module(module_name)
    import translator.ir.nodes as nodes

    importlib.reload(m)
    node_cls = getattr(nodes, spec.node, None)
    if node_cls is None:
        raise RuntimeError(f"unknown IR node class: {spec.node}")

    rules = getattr(m, "AUTOGEN_RULES", None)
    mapping = getattr(rules, "expr_emitters" if spec.kind == "expr" else "stmt_emitters", {})
    if not callable(mapping.get(node_cls)):
        raise RuntimeError(f"generated rule was not registered for {spec.kind}:{spec.node}")


def _eval_after_apply(
    pair_root: Path,
    out_dir: Path,
    features: list[str],
    timeout: int,
    *,
    frontend: str,
) -> dict:
    pairs = load_pairs(pair_root)
    if features:
        wanted = set(features)
        pairs = [pair for pair in pairs if not wanted.isdisjoint(pair.features)]

    results = [
        eval_pair(
            pair,
            out_dir,
            root=pair_root.resolve(),
            timeout=timeout,
            autofix_iters=0,
            compare_reference=False,
            frontend=frontend,
        )
        for pair in pairs
    ]
    return {
        "total": len(results),
        "translate_pass": sum(1 for r in results if r.translate_ok),
        "translate_fail": sum(1 for r in results if not r.translate_ok),
        "results": [r.__dict__ for r in results],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m translator.manual_pairs.learn",
        description="Generate target emitter rules with LLM using manual C/target-language pairs.",
    )
    parser.add_argument("--root", default="dataset/manual_pairs")
    parser.add_argument("--target", default="Cangjie")
    parser.add_argument("--rule", type=_parse_rule_spec, action="append", required=True, help="Rule to generate, e.g. expr:Index or stmt:While.")
    parser.add_argument("--feature", action="append", default=[], help="Select manual examples by feature label. Repeatable.")
    parser.add_argument("--max-pairs", type=int, default=3)
    parser.add_argument("--out-dir", default="dataset/manual_pair_learn")
    parser.add_argument("--backend", choices=["a", "b"], default="b", help="Autogen ruleset/backend to use. Default: b.")
    parser.add_argument("--dump-prompt", action="store_true", help="Write rule prompt files and do not call the LLM.")
    parser.add_argument("--apply", action="store_true", help="Write generated rules into the selected backend autogen ruleset.")
    parser.add_argument("--replace", action="store_true", help="When applying, replace an existing autogen mapping for the same IR node.")
    parser.add_argument("--eval", action="store_true", help="Run manual pair translation after applying rules.")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args(argv)

    pair_root = Path(args.root).resolve()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    backend = resolve_backend(args.backend)

    if args.dump_prompt and (args.apply or args.eval):
        raise RuntimeError("--dump-prompt cannot be combined with --apply or --eval")

    generated: list[dict] = []
    dumped_prompts: list[str] = []
    for spec in args.rule:
        if args.dump_prompt:
            prompt = build_rule_prompt(
                spec,
                target_name=args.target,
                pair_root=pair_root,
                features=list(args.feature),
                max_pairs=args.max_pairs,
            )
            prompt_path = out_dir / f"{spec.kind}_{spec.node}.prompt.md"
            prompt_path.write_text(prompt, encoding="utf-8")
            dumped_prompts.append(str(prompt_path))
            print(f"[learn] wrote prompt {prompt_path}")
            continue

        data = _generate_rule(
            spec,
            target_name=args.target,
            pair_root=pair_root,
            features=list(args.feature),
            max_pairs=args.max_pairs,
        )
        generated.append(data)
        proposal_path = out_dir / f"{spec.kind}_{spec.node}.json"
        proposal_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"[learn] wrote proposal {proposal_path}")

        if args.apply:
            with autogen_backend_env(backend):
                changed = apply_patch(
                    spec.kind,
                    spec.node,
                    str(data["func_name"]),
                    str(data["func_code"]),
                    replace=bool(args.replace),
                )
                _sanity_check_autogen(spec)
            print(f"[learn] applied {spec.kind}:{spec.node} changed={changed}")

    summary: dict[str, object] = {
        "target": args.target,
        "root": str(pair_root),
        "backend": backend.name,
        "autogen_path": str(backend.autogen_path),
        "autogen_module": backend.autogen_module,
        "rules": [{"kind": item["kind"], "node": item["node"], "func_name": item["func_name"]} for item in generated],
        "dumped_prompts": dumped_prompts,
        "applied": bool(args.apply),
        "replace": bool(args.replace),
    }

    if args.eval:
        if not args.apply:
            raise RuntimeError("--eval requires --apply so generated rules are importable")
        eval_summary = _eval_after_apply(
            pair_root,
            out_dir / "eval",
            list(args.feature),
            args.timeout,
            frontend=backend.frontend,
        )
        summary["eval"] = eval_summary
        print(
            "[learn] eval "
            f"total={eval_summary['total']} pass={eval_summary['translate_pass']} "
            f"fail={eval_summary['translate_fail']}"
        )

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[learn] wrote {out_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

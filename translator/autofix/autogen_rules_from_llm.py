from __future__ import annotations
import os
from pathlib import Path
from typing import Literal
from translator.autofix.llm_client import llm_chat_json
from translator.autofix.ruleset_autogen_writer import apply_patch
from translator.manual_pairs.pair_context import build_pair_prompt_context

PROMPT_TEMPLATE = """You will generate a single Python emitter rule for a transpiler.
Target language emitter API:
- You are writing a function used by RuleSet:
  - ExprEmitter: (emitter, expr) -> str
  - StmtEmitter: (emitter, stmt, indent) -> list[str]
- emitter has methods:
  - emitter.emit_expr(expr) -> str
  - emitter.emit_type(ty) -> str
  - emitter.emit_op(op) -> str
  - emitter.emit_unary_op(op) -> str
  - emitter.emit_block(block, indent) -> list[str]
  - emitter.stmt_term: string (may be "" for Cangjie)

IR nodes available (subset):
Expr: Literal, Var, Binary, Unary, Cast
Stmt: ExprStmt, VarDecl, Assign, Return, If, BlockStmt
AddrOf(expr: Expr)
Deref(expr: Expr)
Index(base: Expr, index: Expr)

Task:
- We are missing a rule for: {kind} node `{node}`.
- Generate ONE function implementing emission for this node, matching our style.
- IMPORTANT: Only generate the function. Do NOT generate any RuleSet / AUTOGEN_RULES / mapping dicts.
- Function must be deterministic, minimal, and use indentation: pad = "  " * indent (for stmt)
- No comments.

Output format: JSON ONLY with keys:
- kind: "expr" or "stmt"
- node: node class name (same as input)
- func_name: python function name
- func_code: full python code of the function (def ...)

Constraints:
- Do NOT reference any unknown symbols.
- For stmt emitters, return list[str] lines (no trailing semicolon unless emitter.stmt_term).
- For expr emitters, return a string.
- func_code MUST contain exactly one top-level Python function definition starting with "def ".
- func_code MUST NOT contain "RuleSet", "AUTOGEN_RULES", "expr_emitters", or "stmt_emitters".
- func_code MUST NOT contain any additional top-level statements besides the function.
- DO NOT use C syntax '&' or '*' anywhere in emitted CJ code.
- AddrOf(x) must emit: `inout <x>` (as text).
- Deref(p) must emit: `unsafe {{ <p>.read() }}`
- Index(a,i) must emit: `<a>[<i>]`

Now generate for:
kind={kind}
node={node}
"""

def _manual_pair_context() -> str:
    root = os.environ.get("MANUAL_PAIR_ROOT", "").strip()
    if not root:
        return ""

    features = [
        item.strip()
        for item in os.environ.get("MANUAL_PAIR_FEATURES", "").split(",")
        if item.strip()
    ]
    max_pairs = int(os.environ.get("MANUAL_PAIR_MAX", "3"))
    return build_pair_prompt_context(Path(root), features, max_pairs=max_pairs)

def autogen_one(kind: Literal["expr","stmt"], node: str) -> bool:
    prompt = PROMPT_TEMPLATE.format(kind=kind, node=node)
    context = _manual_pair_context()
    if context:
        prompt = context + "\n\n" + prompt
    data = llm_chat_json(prompt)

    k = data["kind"]
    n = data["node"]
    fn = data["func_name"]
    code = data["func_code"]

    if k not in ("expr","stmt"):
        raise RuntimeError(f"bad kind from llm: {k}")
    if n != node:
        raise RuntimeError(f"node mismatch: expected {node}, got {n}")

    return apply_patch(k, n, fn, code)

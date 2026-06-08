import os
from pathlib import Path
import re
from typing import Literal

DEFAULT_AUTOGEN_PATH = Path(__file__).resolve().parents[1] / "backend" / "ruleset_autogen.py"


def _autogen_path() -> Path:
    override = os.environ.get("AUTOGEN_RULESET_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_AUTOGEN_PATH

HEADER = """

from translator.backend.ruleset import RuleSet
from translator.ir.nodes import *

# Auto-generated rules. Do not edit by hand.

# --- emitters (functions) ---

"""

FOOTER_TEMPLATE = """
# --- ruleset mapping ---

AUTOGEN_RULES = RuleSet(
    expr_emitters={{
{expr_map}
    }},
    stmt_emitters={{
{stmt_map}
    }},
)
"""

def _ensure_file():
    path = _autogen_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(HEADER + FOOTER_TEMPLATE.format(expr_map="", stmt_map=""), encoding="utf-8")

def _read() -> str:
    _ensure_file()
    return _autogen_path().read_text(encoding="utf-8")

def _write(s: str):
    _autogen_path().write_text(s, encoding="utf-8")

def _has_mapping(src: str, kind: str, node: str) -> bool:
    block = _mapping_block(src, kind)
    needle = f"{node}: "
    return needle in block


def _mapping_block_span(src: str, kind: str) -> tuple[int, int, int]:
    key = "expr_emitters" if kind == "expr" else "stmt_emitters"
    needle = f"{key}={{"
    idx = src.find(needle)
    if idx == -1:
        raise RuntimeError(f"autogen file format unexpected ({kind} block)")

    i = idx + len(needle)
    depth = 1
    while i < len(src) and depth > 0:
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1

    if depth != 0:
        raise RuntimeError(f"autogen file format unexpected ({kind} block)")

    return idx, idx + len(needle), i - 1


def _mapping_block(src: str, kind: str) -> str:
    _, body_start, close_brace_pos = _mapping_block_span(src, kind)
    return src[body_start:close_brace_pos]

def _insert_function(src: str, func_name: str, func_code: str) -> str:
    if re.search(rf"^\s*def\s+{re.escape(func_name)}\s*\(", src, re.M):
        return src
    anchor = "\n# --- ruleset mapping ---\n"
    if anchor not in src:
        raise RuntimeError("autogen file format unexpected (missing anchor)")
    return src.replace(anchor, "\n" + func_code.rstrip() + "\n\n" + anchor, 1)

def _replace_mapping(src: str, kind: str, node: str, fn_name: str) -> str:
    key = "expr_emitters" if kind == "expr" else "stmt_emitters"
    _, body_start, close_brace_pos = _mapping_block_span(src, kind)
    block = src[body_start:close_brace_pos]
    pattern = re.compile(rf"^(\s*){re.escape(node)}\s*:\s*[A-Za-z_]\w*\s*,\s*$", re.M)
    replaced_block, n = pattern.subn(rf"\1{node}: {fn_name},", block, count=1)
    if n == 0 and _has_mapping(src, kind, node):
        raise RuntimeError(f"failed to replace existing mapping for {key}.{node}")
    return src[:body_start] + replaced_block + src[close_brace_pos:]


def _insert_mapping(src: str, kind: str, node: str, fn_name: str, *, replace: bool = False) -> str:
    if kind not in ("expr", "stmt"):
        raise ValueError(f"invalid kind: {kind}")
    if node.startswith("emit_"):
        raise ValueError(f"invalid node name (looks like emitter): {node}")
    if not fn_name.startswith("emit_"):
        raise ValueError(f"invalid emitter function name: {fn_name}")

    key = "expr_emitters" if kind == "expr" else "stmt_emitters"

    if _has_mapping(src, kind, node):
        if replace:
            return _replace_mapping(src, kind, node, fn_name)
        return src

    idx, _, close_brace_pos = _mapping_block_span(src, kind)

    line_start = src.rfind("\n", 0, idx) + 1
    line_prefix = src[line_start:idx]
    item_indent = line_prefix + "    "

    entry = f"{item_indent}{node}: {fn_name},\n"
    return src[:close_brace_pos] + entry + src[close_brace_pos:]

def apply_patch(kind: Literal["expr","stmt"], node: str, func_name: str, func_code: str, *, replace: bool = False) -> bool:
    """
    Return True if file changed.
    """
    src = _read()
    before = src
    src = _insert_function(src, func_name, func_code)
    src = _insert_mapping(src, kind, node, func_name, replace=replace)
    changed = (src != before)
    if changed:
        _write(src)
    return changed

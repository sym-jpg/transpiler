

from translator.backend.ruleset import RuleSet
from translator.ir.nodes import *
# Auto-generated rules. Do not edit by hand.

# --- emitters (functions) ---


def emit_addrof_expr(emitter, expr):
    inner = emitter.emit_expr(expr.expr)
    return f"inout {inner}"


def emit_Deref(emitter, expr) -> str:
    inner = emitter.emit_expr(expr.expr)
    return f"unsafe {{ {inner}.read() }}"


def emit_index_expr(emitter, expr):
    base = emitter.emit_expr(expr.base)
    index = emitter.emit_expr(expr.index)
    return f"{base}[Int64({index})]"


def emit_field_expr(emitter, expr):
    base = getattr(expr, "base", None)
    if base is None:
        base = getattr(expr, "obj", None)
    if base is None:
        base = getattr(expr, "object", None)
    field = getattr(expr, "field", None)
    if field is None:
        field = getattr(expr, "name", None)
    if field is None:
        field = getattr(expr, "member", "")
    if base is None:
        return str(field)
    print(f"{emitter.emit_expr(base)}.{field}")
    return f"{emitter.emit_expr(base)}.{field}"


def emit_Arrow(emitter, expr):
    base = getattr(expr, "base", getattr(expr, "lhs", getattr(expr, "ptr", None)))
    member = getattr(expr, "member", getattr(expr, "field", getattr(expr, "name", getattr(expr, "rhs", None))))
    base_s = emitter.emit_expr(base)
    if isinstance(member, str):
        member_s = member
    else:
        member_s = emitter.emit_expr(member)
    return f"(unsafe {{ {base_s}.read() }}).{member_s}"


def emit_InitList(emitter, expr):
    elems = None
    for name in ("elements", "elems", "items", "values", "args"):
        if hasattr(expr, name):
            elems = getattr(expr, name)
            break
    if elems is None:
        elems = []
    parts = [emitter.emit_expr(e) for e in elems]
    return "[" + ", ".join(parts) + "]"


def emit_assign_expr(emitter, expr):
    lhs = getattr(expr, "target", None)
    if lhs is None:
        lhs = getattr(expr, "lhs", None)
    if lhs is None:
        lhs = getattr(expr, "left", None)

    rhs = getattr(expr, "value", None)
    if rhs is None:
        rhs = getattr(expr, "rhs", None)
    if rhs is None:
        rhs = getattr(expr, "right", None)

    rhs_s = emitter.emit_expr(rhs)

    if isinstance(lhs, Deref):
        inner = getattr(lhs, "expr", None)
        if inner is None:
            inner = getattr(lhs, "value", None)
        if inner is None:
            inner = getattr(lhs, "ptr", None)
        p_s = emitter.emit_expr(inner)
        return f"unsafe {{ {p_s}.write({rhs_s}) }}"

    lhs_s = emitter.emit_expr(lhs)
    return f"{lhs_s} = {rhs_s}"


def emit_index(emitter, expr):
    base_s = emitter.emit_expr(expr.base)
    idx_s = emitter.emit_expr(expr.index)
    idx_t = idx_s.strip()
    if idx_t.startswith("Int64(") and idx_t.endswith(")"):
        return f"{base_s}[{idx_s}]"
    return f"{base_s}[Int64({idx_s})]"


# --- ruleset mapping ---

AUTOGEN_RULES = RuleSet(
    expr_emitters={
        AddrOf: emit_addrof_expr,
        Deref: emit_Deref,
        Index: emit_index,
        Field: emit_field_expr,
        Arrow: emit_Arrow,
        InitList: emit_InitList,
        Assign: emit_assign_expr,
    },
    stmt_emitters={
    },
)

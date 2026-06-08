from translator.backend.ruleset import RuleSet
from translator.ir.nodes import *

# Auto-generated rules for emitter B. This file is intentionally separate from
# ruleset_autogen.py so the existing emitter A keeps its behavior.


def emit_addrof_expr(emitter, expr):
    inner = emitter.emit_expr(expr.expr)
    return f"inout {inner}"


def emit_Deref(emitter, expr) -> str:
    inner = emitter.emit_expr(expr.expr)
    return f"unsafe {{ {inner}.read() }}"


def emit_field_expr(emitter, expr):
    base = getattr(expr, "base", None)
    field = getattr(expr, "name", getattr(expr, "field", ""))
    if hasattr(field, "name"):
        field = field.name
    if base is None:
        return str(field)
    return f"{emitter.emit_expr(base)}.{field}"


def emit_Arrow(emitter, expr):
    base_s = emitter.emit_expr(expr.base)
    name = getattr(expr, "name", getattr(expr, "field", ""))
    if hasattr(name, "name"):
        name = name.name
    return f"(unsafe {{ {base_s}.read() }}).{name}"


def emit_assign_expr(emitter, expr):
    lhs = getattr(expr, "target", getattr(expr, "lhs", getattr(expr, "left", None)))
    rhs = getattr(expr, "value", getattr(expr, "rhs", getattr(expr, "right", None)))
    rhs_s = emitter.emit_expr(rhs)
    if isinstance(lhs, Deref):
        p_s = emitter.emit_expr(lhs.expr)
        return f"unsafe {{ {p_s}.write({rhs_s}) }}"
    return f"{emitter.emit_expr(lhs)} = {rhs_s}"


def emit_index(emitter, expr):
    base_s = emitter.emit_expr(expr.base)
    idx_s = emitter.emit_expr(expr.index)
    if idx_s.strip().startswith("Int64("):
        return f"{base_s}[{idx_s}]"
    return f"{base_s}[Int64({idx_s})]"


def emit_literal(emitter, expr):
    ty_s = emitter.emit_type(expr.ty)
    v = expr.value
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        if ty_s.startswith("UInt"):
            bits = "".join(ch for ch in ty_s[4:] if ch.isdigit()) or "32"
            return f"{v & ((1 << int(bits)) - 1)}u{bits}"
        return str(v)
    if isinstance(v, float):
        return repr(v)
    raise TypeError(f"unsupported literal: {type(v)!r}")


def emit_var_expr(emitter, expr):
    return expr.name


def emit_cangjie_binary(emitter, expr):
    lhs = emitter.emit_expr(expr.lhs)
    rhs = emitter.emit_expr(expr.rhs)
    ty = getattr(expr, "ty", None)
    ty_s = emitter.emit_type(expr.ty)
    is_i32 = getattr(ty, "kind", None) == "int" and getattr(ty, "bits", None) == 32 and getattr(getattr(ty, "signed", None), "name", None) == "SIGNED"
    is_u32 = getattr(ty, "kind", None) == "int" and getattr(ty, "bits", None) == 32 and getattr(getattr(ty, "signed", None), "name", None) == "UNSIGNED"
    if expr.op == BinOp.ADD:
        if is_i32:
            return f"cInt32Add({lhs}, {rhs})"
        if is_u32:
            return f"cUInt32Add({lhs}, {rhs})"
    if expr.op == BinOp.SUB:
        if is_i32:
            return f"cInt32Sub({lhs}, {rhs})"
        if is_u32:
            return f"cUInt32Sub({lhs}, {rhs})"
    if expr.op == BinOp.MUL:
        if is_i32:
            return f"cInt32Mul({lhs}, {rhs})"
        if is_u32:
            return f"cUInt32Mul({lhs}, {rhs})"
    if expr.op == BinOp.DIV:
        if is_i32:
            return f"cInt32Div({lhs}, {rhs})"
        if is_u32:
            return f"cUInt32Div({lhs}, {rhs})"
    if expr.op == BinOp.MOD:
        if is_i32:
            return f"cInt32Mod({lhs}, {rhs})"
        if is_u32:
            return f"cUInt32Mod({lhs}, {rhs})"
    return f"({lhs} {emitter.emit_op(expr.op)} {rhs})"


def emit_cangjie_cast(emitter, expr):
    inner = emitter.emit_expr(expr.expr)
    to_ty = expr.to_ty
    from_ty = getattr(expr.expr, "ty", None)
    if (
        getattr(to_ty, "kind", None) == "int"
        and getattr(to_ty, "bits", None) == 32
        and getattr(getattr(to_ty, "signed", None), "name", None) == "UNSIGNED"
        and getattr(from_ty, "kind", None) == "int"
        and getattr(from_ty, "bits", None) == 32
        and getattr(getattr(from_ty, "signed", None), "name", None) == "SIGNED"
    ):
        return f"cInt32ToUInt32({inner})"
    if (
        getattr(to_ty, "kind", None) == "int"
        and getattr(to_ty, "bits", None) == 32
        and getattr(getattr(to_ty, "signed", None), "name", None) == "SIGNED"
        and getattr(from_ty, "kind", None) == "int"
        and getattr(from_ty, "bits", None) == 32
        and getattr(getattr(from_ty, "signed", None), "name", None) == "UNSIGNED"
    ):
        return f"cUInt32ToInt32({inner})"
    return f"{emitter.emit_type(to_ty)}({inner})"


def emit_unary(emitter, expr):
    operand = emitter.emit_expr(expr.operand)
    if expr.op == UnOp.NOT:
        return f"({operand} == 0)"
    return f"{emitter.emit_unary_op(expr.op)}{operand}"


def _default_value_for_type(emitter, ty):
    if ty.kind == "bool":
        return "false"
    if ty.kind == "int":
        return "0u32" if emitter.emit_type(ty).startswith("UInt") else "0"
    if ty.kind == "array":
        n = ty.length or 0
        elem = ty.elem
        inner = _default_value_for_type(emitter, elem) if elem is not None else "0"
        return "[" + ", ".join(inner for _ in range(n)) + "]"
    return "0"


def emit_vardecl(emitter, stmt, indent):
    pad = "  " * indent
    name = stmt.var.name
    ty_s = emitter.emit_type(stmt.var.ty)
    init_s = emitter.emit_expr(stmt.init) if stmt.init is not None else _default_value_for_type(emitter, stmt.var.ty)
    return [f"{pad}var {name}: {ty_s} = {init_s}{emitter.stmt_term}"]


def _index_chain(expr):
    chain = []
    cur = expr
    while isinstance(cur, Index):
        chain.append(cur)
        cur = cur.base
    chain.reverse()
    return cur, chain


def emit_assign(emitter, stmt, indent):
    pad = "  " * indent
    rhs = emitter.emit_expr(stmt.value)
    target = stmt.target

    if isinstance(target, Index):
        root, chain = _index_chain(target)
        if len(chain) > 1:
            root_s = emitter.emit_expr(root)
            indices = [emitter.emit_expr(item.index) for item in chain]
            temps = [emitter.fresh_tmp() for _ in range(len(indices) - 1)]
            lines = [f"{pad}var {temps[0]} = {root_s}[Int64({indices[0]})]{emitter.stmt_term}"]
            for i in range(1, len(temps)):
                lines.append(f"{pad}var {temps[i]} = {temps[i - 1]}[Int64({indices[i]})]{emitter.stmt_term}")
            lines.append(f"{pad}{temps[-1]}[Int64({indices[-1]})] = {rhs}{emitter.stmt_term}")
            for i in range(len(temps) - 2, -1, -1):
                lines.append(f"{pad}{temps[i]}[Int64({indices[i + 1]})] = {temps[i + 1]}{emitter.stmt_term}")
            lines.append(f"{pad}{root_s}[Int64({indices[0]})] = {temps[0]}{emitter.stmt_term}")
            return lines
    return [f"{pad}{emitter.emit_expr(target)} = {rhs}{emitter.stmt_term}"]


def emit_if(emitter, stmt, indent):
    pad = "  " * indent
    lines = [f"{pad}if ({emitter.emit_condition(stmt.cond)}) {{"]
    lines.extend(emitter.emit_block(stmt.then_body, indent + 1))
    if stmt.else_body is not None:
        lines.append(f"{pad}}} else {{")
        lines.extend(emitter.emit_block(stmt.else_body, indent + 1))
    lines.append(f"{pad}}}")
    return lines


def emit_return(emitter, stmt, indent):
    pad = "  " * indent
    return [f"{pad}return {emitter.emit_expr(stmt.value)}{emitter.stmt_term}"]


def emit_expr_stmt(emitter, stmt, indent):
    pad = "  " * indent
    return [f"{pad}{emitter.emit_expr(stmt.expr)}{emitter.stmt_term}"]


def emit_init_list(emitter, expr):
    return "[" + ", ".join(emitter.emit_expr(e) for e in expr.elems) + "]"


def emit_while_stmt(emitter, stmt, indent):
    pad = "  " * indent
    lines = [f"{pad}while ({emitter.emit_condition(stmt.cond)}) {{"]
    lines.extend(emitter.emit_block(stmt.body, indent + 1))
    lines.append(f"{pad}}}")
    return lines


def emit_call_expr(emitter, expr):
    callee = expr.callee
    if hasattr(callee, "ty"):
        callee_s = emitter.emit_expr(callee)
    elif isinstance(callee, str):
        callee_s = callee
    else:
        callee_s = str(callee)

    args_s = []
    for a in (expr.args or []):
        if hasattr(a, "ty"):
            args_s.append(emitter.emit_expr(a))
        else:
            args_s.append(str(a))

    return f"{callee_s}({', '.join(args_s)})"


def emit_cast_expr(emitter, expr):
    return emit_cangjie_cast(emitter, expr)


def emit_conditional_expr(emitter, expr):
    cond = emitter.emit_condition(expr.cond)
    then_s = emitter.emit_expr(expr.then)
    else_s = emitter.emit_expr(expr.else_)
    return f"(if ({cond}) {{ {then_s} }} else {{ {else_s} }})"


def emit_break_stmt(emitter, stmt, indent):
    pad = "  " * indent
    return [f"{pad}break{emitter.stmt_term}"]


def emit_continue_stmt(emitter, stmt, indent):
    pad = "  " * indent
    return [f"{pad}continue{emitter.stmt_term}"]


def emit_block_stmt(emitter, stmt, indent):
    return emitter.emit_block(stmt.block, indent)


# --- ruleset mapping ---

AUTOGEN_RULES = RuleSet(
    expr_emitters={
        AddrOf: emit_addrof_expr,
        Deref: emit_Deref,
        Index: emit_index,
        Field: emit_field_expr,
        Arrow: emit_Arrow,
        InitList: emit_init_list,
        Assign: emit_assign_expr,
        Literal: emit_literal,
        Var: emit_var_expr,
        Binary: emit_cangjie_binary,
        Cast: emit_cast_expr,
        Unary: emit_unary,
        Call: emit_call_expr,
        Conditional: emit_conditional_expr,
    },
    stmt_emitters={
        VarDecl: emit_vardecl,
        Assign: emit_assign,
        If: emit_if,
        Return: emit_return,
        ExprStmt: emit_expr_stmt,
        While: emit_while_stmt,
        Break: emit_break_stmt,
        Continue: emit_continue_stmt,
        BlockStmt: emit_block_stmt,
    },
)

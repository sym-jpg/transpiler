from typing import List

from translator.ir.nodes import (
    Expr, Literal, Var, Cast, Binary,
    Stmt, Assign, Return, Block,
)

def _indent(level: int) -> str:
    return "  " * level


def print_stmt(stmt: Stmt, level: int = 0) -> str:
    if isinstance(stmt, Block):
        lines: List[str] = [f"{_indent(level)}Block"]
        for s in stmt.stmts:
            lines.append(print_stmt(s, level + 1))
        return "\n".join(lines)

    if isinstance(stmt, Assign):
        head = f"{_indent(level)}Assign {stmt.target.name}:{stmt.target.ty.short()} ="
        body = print_expr(stmt.value, level + 1)
        return f"{head}\n{body}"

    if isinstance(stmt, Return):
        head = f"{_indent(level)}Return"
        body = print_expr(stmt.value, level + 1)
        return f"{head}\n{body}"

    return f"Unknown Stmt: {type(stmt).__name__}"


def print_expr(expr: Expr, level: int = 0) -> str:
    if isinstance(expr, Literal):
        return f"{_indent(level)}Literal {expr.value} : {expr.ty.short()}"

    if isinstance(expr, Var):
        return f"{_indent(level)}Var {expr.name} : {expr.ty.short()}"

    if isinstance(expr, Cast):
        lines = [
            f"{_indent(level)}Cast -> {expr.to_ty.short()}",
            print_expr(expr.expr, level + 1),
        ]
        return "\n".join(lines)

    if isinstance(expr, Binary):
        lines = [
            f"{_indent(level)}Binary {expr.op.value} : {expr.ty.short()}",
            print_expr(expr.lhs, level + 1),
            print_expr(expr.rhs, level + 1),
        ]
        return "\n".join(lines)

    return f"Unknown Expr: {type(expr).__name__}"

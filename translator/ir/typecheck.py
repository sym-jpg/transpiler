from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from translator.common.diagnostics import Diagnostic, ErrorCode
from translator.ir.types import Type
from translator.ir.nodes import (
    # top-level
    Function, Block,
    # stmts
    Stmt, VarDecl, Assign, Return, If, While,
    # exprs
    Expr, Literal, Var, Cast, Unary, Binary,
    # ops
    BinOp, UnOp, ExprStmt
)

# ---- helpers ----

def _hint(obj: object) -> str:
    # 轻量 node hint：不依赖复杂位置系统，先把类型/关键字段打出来
    try:
        return repr(obj)
    except Exception:
        return f"<{type(obj).__name__}>"

def _err(msg: str, node: object) -> Diagnostic:
    return Diagnostic(ErrorCode.E_INVALID_IR, msg, node_hint=_hint(node))

def _is_bool(t: Type) -> bool:
    return t.kind == "bool"

def _is_int(t: Type) -> bool:
    return t.kind == "int"

def _is_float(t: Type) -> bool:
    return t.kind == "float"

def _same_type(a: Type, b: Type) -> bool:
    return a == b

def _is_numeric(t: Type) -> bool:
    return _is_int(t) or _is_float(t)

# ---- public API ----

def typecheck_function(fn: Function) -> None:
    # params 是 Var 列表：只检查不重复（可选），以及类型合法性（可选）
    # 目前先不做复杂符号表，最小检查足够。
    typecheck_block(fn.body, fn_ret_ty=fn.ret_ty)

def typecheck_block(block: Block, fn_ret_ty: Type) -> None:
    for s in block.stmts:
        typecheck_stmt(s, fn_ret_ty=fn_ret_ty)

def typecheck_stmt(stmt: Stmt, fn_ret_ty: Type) -> None:
    if isinstance(stmt, VarDecl):
        # init 的类型必须等于 var.ty，或者 init 是显式 Cast 到 var.ty
        if stmt.init is not None:
            t = typecheck_expr(stmt.init)
            if not _same_type(t, stmt.var.ty):
                raise _err(
                    f"VarDecl init type mismatch: var {stmt.var.name}:{stmt.var.ty.short()} "
                    f"but init is {t.short()}",
                    stmt,
                )
        return

    if isinstance(stmt, ExprStmt):
        # 只要 expr 本身能通过 typecheck 就行
        typecheck_expr(stmt.expr)
        return
    
    if isinstance(stmt, Assign):
        vt = stmt.target.ty
        et = typecheck_expr(stmt.value)
        if not _same_type(vt, et):
            raise _err(
                f"Assign type mismatch: target {stmt.target.name}:{vt.short()} "
                f"but value is {et.short()}",
                stmt,
            )
        return

    if isinstance(stmt, Return):
        rt = typecheck_expr(stmt.value)
        if not _same_type(rt, fn_ret_ty):
            raise _err(
                f"Return type mismatch: function returns {fn_ret_ty.short()} "
                f"but returned expr is {rt.short()}",
                stmt,
            )
        return

    if isinstance(stmt, If):
        ct = typecheck_expr(stmt.cond)
        if not _is_bool(ct):
            raise _err(f"If condition must be Bool, got {ct.short()}", stmt.cond)
        typecheck_block(stmt.then_body, fn_ret_ty=fn_ret_ty)
        if stmt.else_body is not None:
            typecheck_block(stmt.else_body, fn_ret_ty=fn_ret_ty)
        return

    if isinstance(stmt, While):
        ct = typecheck_expr(stmt.cond)
        if not _is_bool(ct):
            raise _err(f"While condition must be Bool, got {ct.short()}", stmt.cond)
        typecheck_block(stmt.body, fn_ret_ty=fn_ret_ty)
        return

    raise _err(f"Unknown Stmt node: {type(stmt).__name__}", stmt)

def typecheck_expr(expr: Expr) -> Type:
    # Literal: value 的 Python 类型不强制（因为 bool 是 int 子类会坑）
    # 真正的类型以 expr.ty 为准；这里做“基本一致性检查”（可选）
    if isinstance(expr, Literal):
        # 可选一致性检查：根据 ty.kind 检查 value 的形态
        if expr.ty.kind == "bool":
            if not isinstance(expr.value, bool):
                # 允许 0/1 吗？建议不允许，避免歧义
                raise _err(f"Bool literal expects Python bool, got {type(expr.value).__name__}", expr)
        elif expr.ty.kind == "int":
            if isinstance(expr.value, bool) or not isinstance(expr.value, int):
                raise _err(f"Int literal expects Python int, got {type(expr.value).__name__}", expr)
        elif expr.ty.kind == "float":
            if not isinstance(expr.value, float):
                # 允许 int 自动当 float？不建议，保持显式
                raise _err(f"Float literal expects Python float, got {type(expr.value).__name__}", expr)
        # 返回其 IR 类型
        return expr.ty

    if isinstance(expr, Var):
        return expr.ty

    if isinstance(expr, Cast):
        inner_t = typecheck_expr(expr.expr)
        # Cast 的结果类型必须等于 to_ty，并且 expr.ty 也应该等于 to_ty（你的 Cast.__post_init__ 应该保证）
        if not _same_type(expr.ty, expr.to_ty):
            raise _err(f"Cast node inconsistent: expr.ty={expr.ty.short()} but to_ty={expr.to_ty.short()}", expr)
        # 允许哪些 cast？先放宽：numeric/bool 之间后续再收紧
        # 最小守卫：至少 inner_t 必须是某种可 cast 的类型
        if inner_t.kind not in ("int", "float", "bool"):
            raise _err(f"Cast from unsupported type {inner_t.short()} to {expr.to_ty.short()}", expr)
        return expr.to_ty

    if isinstance(expr, Unary):
        ot = typecheck_expr(expr.operand)
        if expr.op == UnOp.NOT:
            if not _is_bool(ot) or not _is_bool(expr.ty):
                raise _err(f"Unary NOT expects Bool -> Bool, got {ot.short()} -> {expr.ty.short()}", expr)
            return expr.ty
        raise _err(f"Unknown UnOp {expr.op}", expr)

    if isinstance(expr, Binary):
        lt = typecheck_expr(expr.lhs)
        rt = typecheck_expr(expr.rhs)

        # 1) 算术：int/float 同类型 -> 同类型
        if expr.op in (BinOp.ADD, BinOp.SUB, BinOp.MUL, BinOp.DIV):
            if not (_is_numeric(lt) and _same_type(lt, rt) and _same_type(expr.ty, lt)):
                raise _err(
                    f"Arithmetic expects same numeric types: lhs={lt.short()} rhs={rt.short()} result={expr.ty.short()}",
                    expr,
                )
            return expr.ty

        # 2) 比较：numeric 同类型 -> Bool
        if expr.op in (BinOp.LT, BinOp.LE, BinOp.GT, BinOp.GE):
            print(lt)
            print(rt)
            if not (_is_numeric(lt) and _same_type(lt, rt) and _is_bool(expr.ty)):
                raise _err(
                    f"Comparison expects same numeric types -> Bool: lhs={lt.short()} rhs={rt.short()} result={expr.ty.short()}",
                    expr,
                )
            return expr.ty

        # 3) 相等：同类型（int/float/bool）-> Bool
        if expr.op in (BinOp.EQ, BinOp.NE):
            if not (_same_type(lt, rt) and _is_bool(expr.ty) and (lt.kind in ("int", "float", "bool"))):
                raise _err(
                    f"Equality expects same (int/float/bool) types -> Bool: lhs={lt.short()} rhs={rt.short()} result={expr.ty.short()}",
                    expr,
                )
            return expr.ty

        # 4) 逻辑：Bool Bool -> Bool
        if expr.op in (BinOp.LAND, BinOp.LOR):
            if not (_is_bool(lt) and _is_bool(rt) and _is_bool(expr.ty)):
                raise _err(
                    f"Logical expects Bool Bool -> Bool: lhs={lt.short()} rhs={rt.short()} result={expr.ty.short()}",
                    expr,
                )
            return expr.ty

        raise _err(f"Unknown BinOp {expr.op}", expr)

    raise _err(f"Unknown Expr node: {type(expr).__name__}", expr)

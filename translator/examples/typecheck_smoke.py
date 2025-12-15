from __future__ import annotations

from translator.common.diagnostics import Diagnostic
from translator.ir.typecheck import typecheck_function
from translator.ir.types import Type
from translator.ir.nodes import (
    Function, Block,
    VarDecl, Assign, Return, If, While,
    Var, Literal, Binary, Unary, Cast,
    BinOp, UnOp,
)

# ---------- helpers ----------

def run_case(name: str, fn: Function) -> None:
    print(f"\n=== CASE: {name} ===")
    try:
        typecheck_function(fn)
        print("PASS (typecheck ok)")
    except Diagnostic as e:
        print("FAIL (typecheck rejected)")
        print(str(e))


# ---------- cases ----------

def case_ok() -> Function:
    # 正确样例：while + if + bool逻辑 + 比较
    i = Var(name="i", ty=Type.i32())
    sum_ = Var(name="sum", ty=Type.i32())
    ret = Var(name="ret", ty=Type.i32())
    flag = Var(name="flag", ty=Type.bool())

    decls = [
        VarDecl(var=i, init=Literal(ty=Type.i32(), value=0)),
        VarDecl(var=sum_, init=Literal(ty=Type.i32(), value=0)),
        VarDecl(var=flag, init=Literal(ty=Type.bool(), value=True)),
        VarDecl(var=ret, init=Literal(ty=Type.i32(), value=0)),
    ]

    cond_while = Binary(
        ty=Type.bool(),
        op=BinOp.LT,
        lhs=i,
        rhs=Literal(ty=Type.i32(), value=3),
    )

    body_while = Block(stmts=[
        Assign(
            target=sum_,
            value=Binary(ty=Type.i32(), op=BinOp.ADD, lhs=sum_, rhs=i),
        ),
        Assign(
            target=i,
            value=Binary(ty=Type.i32(), op=BinOp.ADD, lhs=i, rhs=Literal(ty=Type.i32(), value=1)),
        ),
    ])

    cond_if = Binary(
        ty=Type.bool(),
        op=BinOp.LAND,
        lhs=flag,
        rhs=Binary(ty=Type.bool(), op=BinOp.GE, lhs=sum_, rhs=Literal(ty=Type.i32(), value=1)),
    )

    then_body = Block(stmts=[
        Assign(target=ret, value=Literal(ty=Type.i32(), value=1)),
    ])
    else_body = Block(stmts=[
        Assign(target=ret, value=Literal(ty=Type.i32(), value=0)),
    ])

    body = Block(stmts=[
        *decls,
        While(cond=cond_while, body=body_while),
        If(cond=cond_if, then_body=then_body, else_body=else_body),
        Return(value=ret),
    ])

    return Function(name="main", params=[], ret_ty=Type.i32(), body=body)


def case_if_cond_not_bool() -> Function:
    # if 条件是 i32（应失败）
    x = Var(name="x", ty=Type.i32())
    body = Block(stmts=[
        VarDecl(var=x, init=Literal(ty=Type.i32(), value=1)),
        If(
            cond=x,  # 错：cond 不是 Bool
            then_body=Block(stmts=[Return(value=Literal(ty=Type.i32(), value=0))]),
            else_body=None,
        ),
        Return(value=Literal(ty=Type.i32(), value=0)),
    ])
    return Function(name="main", params=[], ret_ty=Type.i32(), body=body)


def case_assign_type_mismatch() -> Function:
    # 给 i32 变量赋 bool（应失败）
    x = Var(name="x", ty=Type.i32())
    body = Block(stmts=[
        VarDecl(var=x, init=Literal(ty=Type.i32(), value=0)),
        Assign(target=x, value=Literal(ty=Type.bool(), value=True)),  # 错：bool -> i32
        Return(value=x),
    ])
    return Function(name="main", params=[], ret_ty=Type.i32(), body=body)


def case_return_type_mismatch() -> Function:
    # 函数返回 i32，但 return bool（应失败）
    body = Block(stmts=[
        Return(value=Literal(ty=Type.bool(), value=True)),
    ])
    return Function(name="main", params=[], ret_ty=Type.i32(), body=body)


def case_logical_operands_not_bool() -> Function:
    # and 两边是 i32（应失败）
    a = Var(name="a", ty=Type.i32())
    b = Var(name="b", ty=Type.i32())
    cond = Binary(ty=Type.bool(), op=BinOp.LAND, lhs=a, rhs=b)  # 错：lhs/rhs 不是 bool
    body = Block(stmts=[
        VarDecl(var=a, init=Literal(ty=Type.i32(), value=1)),
        VarDecl(var=b, init=Literal(ty=Type.i32(), value=2)),
        If(cond=cond, then_body=Block(stmts=[Return(value=Literal(ty=Type.i32(), value=0))])),
        Return(value=Literal(ty=Type.i32(), value=0)),
    ])
    return Function(name="main", params=[], ret_ty=Type.i32(), body=body)


def case_comparison_result_not_bool() -> Function:
    # 比较运算结果类型标成 i32（应失败）
    a = Var(name="a", ty=Type.i32())
    b = Var(name="b", ty=Type.i32())
    bad_cmp = Binary(ty=Type.i32(), op=BinOp.LT, lhs=a, rhs=b)  # 错：< 的结果应为 Bool
    body = Block(stmts=[
        VarDecl(var=a, init=Literal(ty=Type.i32(), value=1)),
        VarDecl(var=b, init=Literal(ty=Type.i32(), value=2)),
        If(cond=bad_cmp, then_body=Block(stmts=[Return(value=Literal(ty=Type.i32(), value=0))])),
        Return(value=Literal(ty=Type.i32(), value=0)),
    ])
    return Function(name="main", params=[], ret_ty=Type.i32(), body=body)


def case_bad_literal_python_type() -> Function:
    # Bool literal 却用 int 1（应失败：你的 typecheck 建议不允许 0/1 代替 bool）
    body = Block(stmts=[
        Return(value=Literal(ty=Type.bool(), value=1)),  # 故意传错
    ])
    return Function(name="main", params=[], ret_ty=Type.bool(), body=body)


# 可选：验证 not（如果你实现了 Unary/UnOp.NOT）
def case_unary_not_operand_not_bool() -> Function:
    # not 的操作数是 i32（应失败）
    x = Var(name="x", ty=Type.i32())
    bad = Unary(ty=Type.bool(), op=UnOp.NOT, operand=x)  # 错：operand 不是 bool
    body = Block(stmts=[
        VarDecl(var=x, init=Literal(ty=Type.i32(), value=1)),
        If(cond=bad, then_body=Block(stmts=[Return(value=Literal(ty=Type.i32(), value=0))])),
        Return(value=Literal(ty=Type.i32(), value=0)),
    ])
    return Function(name="main", params=[], ret_ty=Type.i32(), body=body)


def main() -> None:
    run_case("OK baseline", case_ok())
    run_case("IF condition not Bool", case_if_cond_not_bool())
    run_case("Assign type mismatch", case_assign_type_mismatch())
    run_case("Return type mismatch", case_return_type_mismatch())
    run_case("Logical operands not Bool", case_logical_operands_not_bool())
    run_case("Comparison result not Bool", case_comparison_result_not_bool())
    run_case("Bad literal python type", case_bad_literal_python_type())

    # 如果你实现了 Unary/UnOp.NOT 且 typecheck 支持，可以打开这一行
    run_case("Unary NOT operand not Bool", case_unary_not_operand_not_bool())


if __name__ == "__main__":
    main()

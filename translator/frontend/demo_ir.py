# int a;
# int b;
# unsigned int c;

# c = (unsigned int)(a + b);
# return c;

from translator.ir.types import *
from translator.ir.nodes import *

def build_demo() -> Function:
    a = Var(name="a", ty = Type.i32())
    b = Var(name="b", ty = Type.i32())
    c = Var(name="c", ty = Type.u32())
    d = Var(name = "d", ty = Type.bool())
    e = Var(name = "e", ty = Type.bool())

    la = Literal(value= 2, ty= Type.i32())
    lb = Literal(value= 1, ty= Type.i32())

    lc = Literal(value= True, ty= Type.bool())
    ld = Literal(value= 0, ty= Type.i32())
    #(a < b) && !(a == 0)
    decl_a = VarDecl(var=a, init=Literal(ty=Type.i32(), value=1))
    decl_b = VarDecl(var=b, init=Literal(ty=Type.i32(), value=2))

    add_expr = Binary(ty= Type.i32(), op= BinOp.ADD, lhs=a, rhs=b)

    cast_expr = Cast(ty= Type.i32(), to_ty= Type.u32(), expr= add_expr)

    assign_stmt_c = Assign(target= c, value= cast_expr)

    binary_expr = Binary(ty = Type.bool(), op= BinOp.LE, lhs=la, rhs=lb)

    assign_stmt_d = Assign(target= d, value= binary_expr)

    unary_expr = Unary(ty= Type.bool(), op= UnOp.NOT, operand=lc)

    assign_stmt_e = Assign(target= e, value= unary_expr)

    expr1 = Binary(ty= Type.bool(), op= BinOp.LT, lhs= a, rhs= b)
    expr2 = Binary(ty= Type.bool(), op= BinOp.EQ, lhs= a, rhs= ld)
    expr3 = Binary(ty= Type.bool(), op= BinOp.LAND, lhs= expr1, rhs= expr2)
    
    return_stmt = Return(value= expr3)    
    body = Block([decl_a, decl_b, assign_stmt_c, assign_stmt_d, assign_stmt_e, return_stmt])

    return Function(name= "main", params= [], ret_ty= Type.u32(), body= body)

def build_demo_ir() -> Function:
    """
    验收目标：
    1) while：循环累加 sum
    2) if：根据条件给 flag/ret 赋值
    3) 让函数返回类型与 return 匹配（这里用 i32）
    """

    # --- 变量 ---
    i = Var(name="i", ty=Type.i32())
    sum_ = Var(name="sum", ty=Type.i32())
    flag = Var(name="flag", ty=Type.bool())   # 用 bool 验收逻辑/条件
    ret = Var(name="ret", ty=Type.i32())

    # --- 声明 + 初始化 ---
    decl_i = VarDecl(var=i, init=Literal(ty=Type.i32(), value=0))
    decl_sum = VarDecl(var=sum_, init=Literal(ty=Type.i32(), value=0))
    decl_flag = VarDecl(var=flag, init=Literal(ty=Type.bool(), value=True))
    decl_ret = VarDecl(var=ret, init=Literal(ty=Type.i32(), value=0))

    # --- while (i < 10) { sum = sum + i; i = i + 1; } ---
    cond_while = Binary(
        ty=Type.bool(),
        op=BinOp.LT,
        lhs=i,
        rhs=Literal(ty=Type.i32(), value=10),
    )

    sum_plus_i = Binary(
        ty=Type.i32(),
        op=BinOp.ADD,
        lhs=sum_,
        rhs=i,
    )

    i_plus_1 = Binary(
        ty=Type.i32(),
        op=BinOp.ADD,
        lhs=i,
        rhs=Literal(ty=Type.i32(), value=1),
    )

    while_body = Block(stmts=[
        Assign(target=sum_, value=sum_plus_i),
        Assign(target=i, value=i_plus_1),
    ])

    stmt_while = While(cond=cond_while, body=while_body)

    # --- if (flag && (sum >= 45)) { ret = 1; } else { ret = 0; } ---
    cond_sum_ge_45 = Binary(
        ty=Type.bool(),
        op=BinOp.GE,
        lhs=sum_,
        rhs=Literal(ty=Type.i32(), value=45),
    )

    cond_if = Binary(
        ty=Type.bool(),
        op=BinOp.LAND,      # &&
        lhs=flag,
        rhs=cond_sum_ge_45,
    )

    then_body = Block(stmts=[
        Assign(target=ret, value=Literal(ty=Type.i32(), value=1)),
    ])

    else_body = Block(stmts=[
        Assign(target=ret, value=Literal(ty=Type.i32(), value=0)),
    ])

    stmt_if = If(cond=cond_if, then_body=then_body, else_body=else_body)

    # --- return ret; ---
    stmt_return = Return(value=ret)

    body = Block(stmts=[
        decl_i,
        decl_sum,
        decl_flag,
        decl_ret,
        stmt_while,
        stmt_if,
        stmt_return,
    ])

    return Function(
        name="main",
        params=[],
        ret_ty=Type.i32(),
        body=body,
    )
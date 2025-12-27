from clang.cindex import Cursor, CursorKind
from translator.ir.nodes import Literal, Var, Binary
from translator.ir.types import Type
from translator.ir.nodes import BinOp
from translator.ir.nodes import VarDecl, Assign, Return, Var, While, If, ExprStmt, BlockStmt
from translator.ir.nodes import Block, Function

OPS = {"+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=", "&&", "||", "="}

UNARY_OPS = {"++", "--"}
COMPOUND_OPS = {"+=": "+", "-=": "-", "*=": "*", "/=": "/"}

def _as_block_from_stmt_cursor(c):
    if c.kind == CursorKind.COMPOUND_STMT:
        return lower_block(c)
    else:
        s = lower_stmt(c)
        return Block(stmts=[] if s is None else [s])

def _lower_maybe_stmt(c):
    if c is None:
        return None
    return lower_stmt(c)

def _true_expr():
    return Literal(ty=Type.bool(), value=True)

def _find_token(cur, candidates: set[str]) -> str | None:
    for tok in cur.get_tokens():
        if tok.spelling in candidates:
            return tok.spelling
    return None

def _unary_op(cur) -> str | None:
    return _find_token(cur, UNARY_OPS)

def _compound_op(cur) -> str | None:
    return _find_token(cur, set(COMPOUND_OPS.keys()))

def _binary_operator_spelling(cur: Cursor) -> str:
    kids = list(cur.get_children())
    if len(kids) != 2:
        raise NotImplementedError("binary operator without exactly 2 children")

    lhs, rhs = kids[0], kids[1]

    lhs_end = lhs.extent.end.offset
    rhs_start = rhs.extent.start.offset

    candidates = []
    for tok in cur.get_tokens():
        s = tok.spelling
        if s in OPS:
            t_start = tok.extent.start.offset
            t_end = tok.extent.end.offset
            if lhs_end <= t_start and t_end <= rhs_start:
                candidates.append((t_start, s))

    if not candidates:
        last = None
        for tok in cur.get_tokens():
            if tok.spelling in OPS:
                last = tok.spelling
        if last is None:
            raise NotImplementedError("Cannot find binary operator token")
        return last

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]



_BINOP_MAP = {
    "+": BinOp.ADD,
    "-": BinOp.SUB,
    "*": BinOp.MUL,
    "/": BinOp.DIV,

    "<": BinOp.LT,
    "<=": BinOp.LE,
    ">": BinOp.GT,
    ">=": BinOp.GE,
    "==": BinOp.EQ,
    "!=": BinOp.NE,

    "&&": BinOp.LAND,
    "||": BinOp.LOR,
}

_BOOL_RESULT = {BinOp.LT, BinOp.LE, BinOp.GT, BinOp.GE, BinOp.EQ, BinOp.NE, BinOp.LAND, BinOp.LOR}


def lower_function(cursor):
    assert cursor.kind == CursorKind.FUNCTION_DECL
    body = None
    for c in cursor.get_children():
        if c.kind == CursorKind.COMPOUND_STMT:
            body=lower_block(c)

    assert body is not None
    
    return Function(
        name=cursor.spelling,
        params=[],
        ret_ty=Type.i32(),
        body=body,
    )

def lower_block(cur: Cursor) -> Block:
    stmts = []
    for child in cur.get_children():
        s = lower_stmt(child)
        if s is None:
            continue
        stmts.append(s)
    return Block(stmts=stmts)

def lower_stmt(cursor):
    if cursor.kind == CursorKind.DECL_STMT:
        var_decl = next(cursor.get_children())
        assert var_decl.kind == CursorKind.VAR_DECL

        name = var_decl.spelling
        ty = Type.i32()

        children = list(var_decl.get_children())
        assert len(children) == 1
        init = lower_expr(children[0])

        return VarDecl(
            var=Var(name=name, ty=ty),
            init=init,
        )

    if cursor.kind == CursorKind.RETURN_STMT:
        children = list(cursor.get_children())
        assert len(children) == 1
        value = lower_expr(children[0])
        return Return(value=value)
    
    if cursor.kind == CursorKind.WHILE_STMT:
        kids = list(cursor.get_children())
        assert len(kids) >= 2
        cond = lower_expr(kids[0])

        body_cur = kids[1]
        if body_cur.kind == CursorKind.COMPOUND_STMT:
            body = lower_block(body_cur)
        else:
            body = Block(stmts=[lower_stmt(body_cur)])
        return While(cond=cond, body=body)
    
    if cursor.kind == CursorKind.IF_STMT:
        kids = list(cursor.get_children())
        assert len(kids) in (2, 3)
        cond = lower_expr(kids[0])

        then_cur = kids[1]
        then_body = lower_block(then_cur) if then_cur.kind == CursorKind.COMPOUND_STMT else Block(stmts=[lower_stmt(then_cur)])

        else_body = None
        if len(kids) == 3:
            else_cur = kids[2]
            else_body = lower_block(else_cur) if else_cur.kind == CursorKind.COMPOUND_STMT else Block(stmts=[lower_stmt(else_cur)])

        return If(cond=cond, then_body=then_body, else_body=else_body)
    
    if cursor.kind == CursorKind.COMPOUND_ASSIGNMENT_OPERATOR:
        op_sp = _compound_op(cursor)
        if op_sp is None:
            raise NotImplementedError("Unsupported compound assign operator")

        lhs_cur, rhs_cur = list(cursor.get_children())
        lhs_ir = lower_expr(lhs_cur)
        if not isinstance(lhs_ir, Var):
            raise NotImplementedError("compound assign lhs must be Var")

        rhs_ir = lower_expr(rhs_cur)

        # 把 "+=" desugar 成: lhs = lhs + rhs
        sym = COMPOUND_OPS[op_sp]
        if sym == "+":
            bop = BinOp.ADD
        elif sym == "-":
            bop = BinOp.SUB
        elif sym == "*":
            bop = BinOp.MUL
        elif sym == "/":
            bop = BinOp.DIV
        else:
            raise NotImplementedError(op_sp)

        value = Binary(ty=lhs_ir.ty, op=bop, lhs=lhs_ir, rhs=rhs_ir)
        return Assign(target=lhs_ir, value=value)
    
    if cursor.kind == CursorKind.UNARY_OPERATOR:
        op_sp = _unary_op(cursor)
        if op_sp in {"++", "--"}:
            (child,) = list(cursor.get_children())
            target = lower_expr(child)
            if not isinstance(target, Var):
                raise NotImplementedError("++/-- target must be Var")

            one = Literal(ty=target.ty, value=1)
            bop = BinOp.ADD if op_sp == "++" else BinOp.SUB
            value = Binary(ty=target.ty, op=bop, lhs=target, rhs=one)
            return Assign(target=target, value=value)
        
    if cursor.kind == CursorKind.FOR_STMT:
        kids = list(cursor.get_children())
        if not kids:
            raise NotImplementedError("Empty FOR_STMT")

        body_cur = kids[-1]
        head = kids[:-1]  # init/cond/inc candidates（可能为空）

        init_cur = head[0] if len(head) >= 1 else None
        cond_cur = head[1] if len(head) >= 2 else None
        inc_cur  = head[2] if len(head) >= 3 else None

        init_stmt = _lower_maybe_stmt(init_cur)

        cond_expr = _true_expr() if cond_cur is None else lower_expr(cond_cur)

        inc_stmt = _lower_maybe_stmt(inc_cur)

        body_block = _as_block_from_stmt_cursor(body_cur)
        new_body = list(body_block.stmts)
        if inc_stmt is not None:
            new_body.append(inc_stmt)

        loop = While(cond=cond_expr, body=Block(stmts=new_body))

        out = []
        if init_stmt is not None:
            out.append(init_stmt)
        out.append(loop)
        a= BlockStmt(block=Block(stmts=out))
        print(a)
        return a

    elif cursor.kind.is_expression():
        op = _binary_operator_spelling(cursor)
        if op == "=":
            lhs_cur, rhs_cur = list(cursor.get_children())
            lhs_ir = lower_expr(lhs_cur)
            if not isinstance(lhs_ir, Var):
                raise NotImplementedError("assignment lhs must be Var")
            rhs_ir = lower_expr(rhs_cur)
            return Assign(target=lhs_ir, value=rhs_ir)
        else:
            e = lower_expr(cursor)
        # 你可以两种策略选一种：
        # 1) 统一包 ExprStmt（推荐）
        return ExprStmt(expr=e)
    raise NotImplementedError(cursor.kind)



def lower_expr(cursor: Cursor):
    if cursor.kind == CursorKind.UNEXPOSED_EXPR:
        children = list(cursor.get_children())
        assert len(children) == 1
        return lower_expr(children[0])

    if cursor.kind == CursorKind.INTEGER_LITERAL:
        token = next(cursor.get_tokens())
        value = int(token.spelling)
        return Literal(ty=Type.i32(), value=value)

    if cursor.kind == CursorKind.DECL_REF_EXPR:
        name = cursor.spelling
        return Var(name=name, ty=Type.i32())

    if cursor.kind == CursorKind.BINARY_OPERATOR:
        kids = list(cursor.get_children())
        assert len(kids) == 2
        lhs = lower_expr(kids[0])
        rhs = lower_expr(kids[1])

        op_sp = _binary_operator_spelling(cursor)
        ir_op = _BINOP_MAP.get(op_sp)
        if ir_op is None:
            raise NotImplementedError(f"Unsupported binary operator: {op_sp}")

        ty = Type.bool() if ir_op in _BOOL_RESULT else Type.i32()
        return Binary(ty=ty, op=ir_op, lhs=lhs, rhs=rhs)

    raise NotImplementedError(cursor.kind)

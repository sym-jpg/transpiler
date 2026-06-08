import re

from clang.cindex import Cursor, CursorKind, TypeKind
from translator.ir.nodes import Literal, Stmt, Var, Binary, AddrOf, Deref, Index, Expr, InitList, Cast, Break, Continue
from translator.ir.types import Type
from translator.ir.nodes import BinOp
from translator.ir.nodes import VarDecl, Assign, Return, While, If, ExprStmt, BlockStmt, Call, Deref, Index, Arrow, Field, StructDecl, InitList
from translator.ir.nodes import Block, Function, GlobalVar, FieldDecl, Module

OPS = {
    "+", "-", "*", "/", "%",
    "<", "<=", ">", ">=", "==", "!=",
    "&&", "||", "=",
    "&", "|", "^", "<<", ">>",
    ",",
}

UNARY_OPS = {"++", "--"}
UNARY_EXPR_OPS = {"&", "*", "!", "~", "+", "-"}

_TMP_COUNTER = 0

def _fresh_tmp(prefix: str = "__c_expr_tmp") -> str:
    global _TMP_COUNTER
    name = f"{prefix}_{_TMP_COUNTER}"
    _TMP_COUNTER += 1
    return name

def _unary_expr_op(cur) -> str | None:
    return _find_token(cur, UNARY_EXPR_OPS)

COMPOUND_OPS = {
    "+=": "+",
    "-=": "-",
    "*=": "*",
    "/=": "/",
    "%=": "%",
    "&=": "&",
    "|=": "|",
    "^=": "^",
    "<<=": "<<",
    ">>=": ">>",
}

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

def _break_condition(cond: Expr) -> Expr:
    if getattr(cond.ty, "kind", None) == "bool":
        return Binary(ty=Type.bool(), op=BinOp.EQ, lhs=cond, rhs=Literal(ty=Type.bool(), value=False))
    return Binary(ty=Type.bool(), op=BinOp.EQ, lhs=cond, rhs=Literal(ty=cond.ty, value=0))

def _truth_condition(expr: Expr) -> Expr:
    if getattr(expr.ty, "kind", None) == "bool":
        return expr
    return Binary(ty=Type.bool(), op=BinOp.NE, lhs=expr, rhs=Literal(ty=expr.ty, value=0))

def _find_token(cur, candidates: set[str]) -> str | None:
    for tok in cur.get_tokens():
        if tok.spelling in candidates:
            return tok.spelling
    return None

def _unary_op(cur) -> str | None:
    return _find_token(cur, UNARY_OPS)

def _is_postfix_unary(cur: Cursor, operand: Cursor) -> bool:
    for tok in cur.get_tokens():
        if tok.spelling in UNARY_OPS:
            return tok.extent.start.offset >= operand.extent.end.offset
    return False

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
    "%": BinOp.MOD,

    "&": BinOp.BIT_AND,
    "|": BinOp.BIT_OR,
    "^": BinOp.BIT_XOR,
    "<<": BinOp.SHL,
    ">>": BinOp.SHR,

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


def lower_function(cursor: Cursor) -> Function:
    assert cursor.kind == CursorKind.FUNCTION_DECL

    body: Block | None = None
    params: list[Var] = []

    for c in cursor.get_children():
        if c.kind == CursorKind.PARM_DECL:
            params.append(Var(name=c.spelling, ty=lower_type(c.type)))
        elif c.kind == CursorKind.COMPOUND_STMT:
            body = lower_block(c)

    assert body is not None

    return Function(
        name=cursor.spelling,
        params=params,
        ret_ty=lower_type(cursor.result_type),
        body=body,
    )

def lower_block(cur: Cursor) -> Block:
    raw_stmts: list[Stmt] = []
    for child in cur.get_children():
        s = lower_stmt(child)
        if s is None:
            continue

        # flatten BlockStmt
        if isinstance(s, BlockStmt):
            raw_stmts.extend(s.block.stmts)
        else:
            raw_stmts.append(s)

    # peephole: VarDecl without init + immediate Assign to same var → merge
    stmts: list[Stmt] = []
    i = 0
    while i < len(raw_stmts):
        cur_s = raw_stmts[i]

        # peephole: VarDecl without init + Assign to same var
        if isinstance(cur_s, VarDecl) and cur_s.init is None:
            decl: VarDecl = cur_s

            # lookahead for Assign
            if i + 1 < len(raw_stmts) and isinstance(raw_stmts[i + 1], Assign):
                assign: Assign = raw_stmts[i + 1]

                # match same variable
                if isinstance(assign.target, Var) and assign.target.name == decl.var.name:
                    # merge
                    merged = VarDecl(var=decl.var, init=assign.value)
                    stmts.append(merged)
                    i += 2
                    continue

            # no merge
            stmts.append(decl)
            i += 1
            continue

        stmts.append(cur_s)
        i += 1

    return Block(stmts=stmts)

def lower_type(t) -> Type:
    if getattr(t, "kind", None) == TypeKind.CONSTANTARRAY:

        length = int(t.element_count)

        elem = lower_type(t.element_type)

        arr_ctor = getattr(Type, "array", None)

        if callable(arr_ctor):

            return arr_ctor(elem, length)

        return Type(kind="array", bits=None, signed=None, elem=elem, length=length, name=None)
    s = (t.spelling or "").strip()
    s = re.sub(r"\b(const|volatile|restrict)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()

    m = re.match(r"^(?P<base>.+?)\s*\[\s*(?P<n>\d*)\s*\]\s*$", s)
    if m is not None:
        base_s = m.group("base").strip()
        n_txt = m.group("n")
        n = int(n_txt) if n_txt.isdigit() else None

        class _Shim:
            def __init__(self, spelling: str):
                self.spelling = spelling
        elem = lower_type(_Shim(base_s))

        arr_ctor = getattr(Type, "array", None)
        if callable(arr_ctor):
            return arr_ctor(elem, n)

        ptr_ctor = getattr(Type, "ptr", None)
        if callable(ptr_ctor):
            return ptr_ctor(elem)
        return Type.i32()

    ptr_depth = s.count("*")
    if ptr_depth > 0:
        base_s = s.replace("*", " ").strip()

        class _Shim:
            def __init__(self, spelling: str):
                self.spelling = spelling
        ty = lower_type(_Shim(base_s))

        ptr_ctor = getattr(Type, "ptr", None)
        if callable(ptr_ctor):
            for _ in range(ptr_depth):
                ty = ptr_ctor(ty)
            return ty
        return Type.i32()

    if s.startswith("struct "):
        name = s[len("struct "):].strip()
        ty = Type.struct(name)
        return ty

    if s in ("_Bool", "bool"):
        return Type.bool()

    if s == "void":
        return Type.void()

    if s in (
        "unsigned",
        "unsigned int",
        "unsigned long",
        "unsigned long long",
        "uint32_t",
    ):
        return Type.u32()

    if s in (
        "int",
        "long",
        "int32_t",
    ):
        return Type.i32()

    return Type.i32()


# Unified helper for extracting VAR_DECL initializer
def _lower_vardecl_init(vd: Cursor) -> Expr | None:
    init_cur = _vardecl_init_cursor(vd)
    return lower_expr(init_cur) if init_cur is not None else None


def _vardecl_init_cursor(vd: Cursor) -> Cursor | None:
    kids = list(vd.get_children())
    # TYPE_REF is not part of initializer semantics.
    kids = [k for k in kids if k.kind != CursorKind.TYPE_REF]

    if not kids:
        return None
    init_list = next((k for k in kids if k.kind == CursorKind.INIT_LIST_EXPR), None)
    if init_list is not None:
        return init_list

    type_spelling = (vd.type.spelling or "").strip()
    is_array_decl = "[" in type_spelling and "]" in type_spelling

    if is_array_decl:
        meaningful = [
            k for k in kids
            if k.kind not in {
                CursorKind.INTEGER_LITERAL,
                CursorKind.UNEXPOSED_EXPR,
                CursorKind.PAREN_EXPR,
            }
        ]
        if not meaningful:
            return None

    expr_kids = [k for k in kids if k.kind.is_expression()]
    if expr_kids:
        return expr_kids[-1]

    wrap_kids = [k for k in kids if k.kind in {CursorKind.UNEXPOSED_EXPR, CursorKind.PAREN_EXPR}]
    if wrap_kids:
        return wrap_kids[-1]

    return None

def lower_stmt(cursor):
    if cursor.kind == CursorKind.DECL_STMT:
        decls: list[Stmt] = []
        for vd in cursor.get_children():
            if vd.kind != CursorKind.VAR_DECL:
                raise NotImplementedError(vd.kind)

            name = vd.spelling
            ty = lower_type(vd.type)
            var = Var(name=name, ty=ty)

            init_cur = _vardecl_init_cursor(vd)
            if init_cur is None:
                decls.append(VarDecl(var=var, init=None))
            else:
                effects, init = lower_expr_effectful(init_cur)
                decls.extend(effects)
                decls.append(VarDecl(var=var, init=init))

        return BlockStmt(Block(stmts=decls))

    if cursor.kind == CursorKind.RETURN_STMT:
        children = list(cursor.get_children())
        assert len(children) == 1
        effects, value = lower_expr_effectful(children[0])
        out: list[Stmt] = [*effects, Return(value=value)]
        return BlockStmt(Block(out)) if effects else out[-1]
    
    if cursor.kind == CursorKind.WHILE_STMT:
        kids = list(cursor.get_children())
        assert len(kids) >= 2
        cond_effects, cond = lower_expr_effectful(kids[0])

        body_cur = kids[1]
        if body_cur.kind == CursorKind.COMPOUND_STMT:
            body = lower_block(body_cur)
        else:
            body = Block(stmts=[lower_stmt(body_cur)])
        if cond_effects:
            body = Block(stmts=[*cond_effects, If(cond=_break_condition(cond), then_body=Block(stmts=[Break()])), *body.stmts])
            cond = _true_expr()
        return While(cond=cond, body=body)
    
    if cursor.kind == CursorKind.IF_STMT:
        kids = list(cursor.get_children())
        assert len(kids) in (2, 3)
        cond_effects, cond = lower_expr_effectful(kids[0])

        then_cur = kids[1]
        then_body = lower_block(then_cur) if then_cur.kind == CursorKind.COMPOUND_STMT else Block(stmts=[lower_stmt(then_cur)])

        else_body = None
        if len(kids) == 3:
            else_cur = kids[2]
            else_body = lower_block(else_cur) if else_cur.kind == CursorKind.COMPOUND_STMT else Block(stmts=[lower_stmt(else_cur)])

        stmt = If(cond=cond, then_body=then_body, else_body=else_body)
        if cond_effects:
            return BlockStmt(Block([*cond_effects, stmt]))
        return stmt
    
    if cursor.kind == CursorKind.COMPOUND_ASSIGNMENT_OPERATOR:
        effects, _ = lower_expr_effectful(cursor)
        return BlockStmt(Block(effects)) if len(effects) != 1 else effects[0]
    
    if cursor.kind == CursorKind.UNARY_OPERATOR:
        op_sp = _unary_op(cursor)
        if op_sp in {"++", "--"}:
            (child,) = list(cursor.get_children())
            effects, target = lower_expr_effectful(child)
            if not _is_lvalue(target):
                raise NotImplementedError(
                    f"++/-- target must be lvalue, got {type(target).__name__}"
                )

            one = Literal(ty=target.ty, value=1)
            bop = BinOp.ADD if op_sp == "++" else BinOp.SUB
            value = Binary(ty=target.ty, op=bop, lhs=target, rhs=one)
            out: list[Stmt] = [*effects, Assign(target=target, value=value)]
            return BlockStmt(Block(out)) if effects else out[-1]
        
    if cursor.kind == CursorKind.BREAK_STMT:
        return Break()

    if cursor.kind == CursorKind.CONTINUE_STMT:
        return Continue()

    if cursor.kind == CursorKind.FOR_STMT:
        kids = list(cursor.get_children())
        if not kids:
            raise NotImplementedError("Empty FOR_STMT")

        body_cur = kids[-1]
        head = kids[:-1]

        init_cur = head[0] if len(head) >= 1 else None
        cond_cur = head[1] if len(head) >= 2 else None
        inc_cur = head[2] if len(head) >= 3 else None

        if init_cur is not None and init_cur.kind == CursorKind.NULL_STMT:
            init_cur = None
        if cond_cur is not None and cond_cur.kind == CursorKind.NULL_STMT:
            cond_cur = None
        if inc_cur is not None and inc_cur.kind == CursorKind.NULL_STMT:
            inc_cur = None

        init_stmt = _lower_maybe_stmt(init_cur)
        cond_effects: list[Stmt] = []
        if cond_cur is None:
            cond_expr = _true_expr()
        else:
            cond_effects, cond_expr = lower_expr_effectful(cond_cur)
        inc_stmt = _lower_maybe_stmt(inc_cur)

        body_block = _as_block_from_stmt_cursor(body_cur)
        while_body_stmts = []
        if cond_effects:
            while_body_stmts.extend(cond_effects)
            while_body_stmts.append(If(cond=_break_condition(cond_expr), then_body=Block(stmts=[Break()])))
            cond_expr = _true_expr()
        while_body_stmts.extend(body_block.stmts)
        if inc_stmt is not None:
            while_body_stmts.append(inc_stmt)

        loop = While(cond=cond_expr, body=Block(stmts=while_body_stmts))

        out: list[Stmt] = []
        if init_stmt is not None:
            out.append(init_stmt)
        out.append(loop)

        return BlockStmt(block=Block(stmts=out))

    elif cursor.kind.is_expression():
        if cursor.kind != CursorKind.BINARY_OPERATOR:
            effects, e = lower_expr_effectful(cursor)
            out: list[Stmt] = [*effects, ExprStmt(expr=e)]
            return BlockStmt(Block(out)) if effects else out[-1]

        op = _binary_operator_spelling(cursor)
        if op == "=":
            lhs_cur, rhs_cur = list(cursor.get_children())
            lhs_ir = lower_expr(lhs_cur)

            if not _is_lvalue(lhs_ir):
                raise NotImplementedError(
                    f"assignment lhs must be lvalue (Var/Deref/Index/Field/Arrow), got {type(lhs_ir).__name__}"
                )

            effects, rhs_ir = lower_expr_effectful(rhs_cur)
            out: list[Stmt] = [*effects, Assign(target=lhs_ir, value=rhs_ir)]
            return BlockStmt(Block(out)) if effects else out[-1]

        else:
            effects, e = lower_expr_effectful(cursor)

        out: list[Stmt] = [*effects, ExprStmt(expr=e)]
        return BlockStmt(Block(out)) if effects else out[-1]
    
    raise NotImplementedError(cursor.kind)

_C_INT_SUFFIX_RE = re.compile(r"(?i)(u|l)+$")

def parse_c_int_literal(s: str) -> int:
    s = s.strip()
    s = _C_INT_SUFFIX_RE.sub("", s)

    return int(s, 0)

def _binop_from_symbol(sym: str) -> BinOp:
    op = _BINOP_MAP.get(sym)
    if op is None:
        raise NotImplementedError(f"Unsupported binary operator: {sym}")
    return op


def _is_lvalue(e: Expr) -> bool:
    return isinstance(e, (Var, Deref, Index, Field, Arrow))


def _combine_effects(*groups: list[Stmt]) -> list[Stmt]:
    out: list[Stmt] = []
    for group in groups:
        out.extend(group)
    return out


def lower_expr_effectful(cursor: Cursor) -> tuple[list[Stmt], Expr]:

    if cursor.kind == CursorKind.COMPOUND_ASSIGNMENT_OPERATOR:
        op_sp = _compound_op(cursor)
        if op_sp is None or op_sp not in COMPOUND_OPS:
            raise NotImplementedError(f"Unsupported compound assign operator: {op_sp}")

        lhs_cur, rhs_cur = list(cursor.get_children())
        lhs_effects, lhs_ir = lower_expr_effectful(lhs_cur)
        if not _is_lvalue(lhs_ir):
            raise NotImplementedError(
                f"compound assign lhs must be lvalue, got {type(lhs_ir).__name__}"
            )
        rhs_effects, rhs_ir = lower_expr_effectful(rhs_cur)
        bop = _binop_from_symbol(COMPOUND_OPS[op_sp])
        value = Binary(ty=lhs_ir.ty, op=bop, lhs=lhs_ir, rhs=rhs_ir)
        return _combine_effects(lhs_effects, rhs_effects, [Assign(target=lhs_ir, value=value)]), lhs_ir

    unwrap_kinds = {CursorKind.UNEXPOSED_EXPR, CursorKind.PAREN_EXPR}
    implicit_cast = getattr(CursorKind, "IMPLICIT_CAST_EXPR", None)
    if implicit_cast is not None:
        unwrap_kinds.add(implicit_cast)
    if cursor.kind in unwrap_kinds:
        children = list(cursor.get_children())
        if len(children) == 1:
            return lower_expr_effectful(children[0])
        if cursor.kind == CursorKind.UNEXPOSED_EXPR and len(children) == 0:
            for tok in cursor.get_tokens():
                s = tok.spelling
                if s and (s[0].isalpha() or s[0] == "_"):
                    return [], Var(name=s, ty=lower_type(cursor.type))
        raise NotImplementedError(f"unwrap node has unexpected children: {cursor.kind} len={len(children)}")

    if cursor.kind == CursorKind.BINARY_OPERATOR:
        kids = list(cursor.get_children())
        assert len(kids) == 2

        op_sp = _binary_operator_spelling(cursor)
        if op_sp == "=":
            lhs_effects, lhs_ir = lower_expr_effectful(kids[0])
            if not _is_lvalue(lhs_ir):
                raise NotImplementedError(
                    f"assignment lhs must be lvalue (Var/Deref/Index/Field/Arrow), got {type(lhs_ir).__name__}"
                )
            rhs_effects, rhs_ir = lower_expr_effectful(kids[1])
            return _combine_effects(lhs_effects, rhs_effects, [Assign(target=lhs_ir, value=rhs_ir)]), lhs_ir

        if op_sp == ",":
            lhs_effects, _ = lower_expr_effectful(kids[0])
            rhs_effects, rhs = lower_expr_effectful(kids[1])
            return _combine_effects(lhs_effects, rhs_effects), rhs

        if op_sp in {"&&", "||"}:
            lhs_effects, lhs = lower_expr_effectful(kids[0])
            tmp = Var(name=_fresh_tmp("__c_logic_tmp"), ty=Type.bool())
            rhs_effects, rhs = lower_expr_effectful(kids[1])
            rhs_assign = Assign(target=tmp, value=_truth_condition(rhs))

            if op_sp == "&&":
                return (
                    _combine_effects(
                        lhs_effects,
                        [
                            VarDecl(var=tmp, init=Literal(ty=Type.bool(), value=False)),
                            If(
                                cond=_truth_condition(lhs),
                                then_body=Block(stmts=[*rhs_effects, rhs_assign]),
                            ),
                        ],
                    ),
                    tmp,
                )

            return (
                _combine_effects(
                    lhs_effects,
                    [
                        VarDecl(var=tmp, init=Literal(ty=Type.bool(), value=True)),
                        If(
                            cond=_truth_condition(lhs),
                            then_body=Block(stmts=[]),
                            else_body=Block(stmts=[*rhs_effects, rhs_assign]),
                        ),
                    ],
                ),
                tmp,
            )

        lhs_effects, lhs = lower_expr_effectful(kids[0])
        rhs_effects, rhs = lower_expr_effectful(kids[1])
        ir_op = _binop_from_symbol(op_sp)
        ty = Type.bool() if ir_op in _BOOL_RESULT else Type.i32()
        return _combine_effects(lhs_effects, rhs_effects), Binary(ty=ty, op=ir_op, lhs=lhs, rhs=rhs)

    if cursor.kind == CursorKind.CSTYLE_CAST_EXPR:
        kids = list(cursor.get_children())
        kids = [k for k in kids if k.kind != CursorKind.TYPE_REF]
        if not kids:
            raise NotImplementedError("CSTYLE_CAST_EXPR without operand")
        effects, expr = lower_expr_effectful(kids[-1])
        ty = lower_type(cursor.type)
        return effects, Cast(to_ty=ty, expr=expr, ty=ty)

    if cursor.kind == CursorKind.ARRAY_SUBSCRIPT_EXPR:
        kids = list(cursor.get_children())
        if len(kids) != 2:
            raise NotImplementedError("ARRAY_SUBSCRIPT_EXPR without 2 children")
        base_effects, base = lower_expr_effectful(kids[0])
        idx_effects, idx = lower_expr_effectful(kids[1])
        elem = getattr(getattr(base, "ty", None), "elem", None)
        ty = elem if elem is not None else Type.i32()
        return _combine_effects(base_effects, idx_effects), Index(ty=ty, base=base, index=idx)

    if cursor.kind == CursorKind.UNARY_OPERATOR:
        inc_op = _unary_op(cursor)
        if inc_op in {"++", "--"}:
            kids = list(cursor.get_children())
            if len(kids) != 1:
                raise NotImplementedError("++/-- without exactly one operand")
            operand_cur = kids[0]
            target_effects, target = lower_expr_effectful(operand_cur)
            if not _is_lvalue(target):
                raise NotImplementedError(
                    f"++/-- target must be lvalue, got {type(target).__name__}"
                )

            one = Literal(ty=target.ty, value=1)
            bop = BinOp.ADD if inc_op == "++" else BinOp.SUB
            value = Binary(ty=target.ty, op=bop, lhs=target, rhs=one)
            assign = Assign(target=target, value=value)

            if _is_postfix_unary(cursor, operand_cur):
                tmp = Var(name=_fresh_tmp(), ty=target.ty)
                return (
                    _combine_effects(
                        target_effects,
                        [VarDecl(var=tmp, init=target), assign],
                    ),
                    tmp,
                )

            return _combine_effects(target_effects, [assign]), target

        op_sp = _unary_expr_op(cursor)
        kids = list(cursor.get_children())
        if not kids:
            raise NotImplementedError("UNARY_OPERATOR without operand")
        effects, operand = lower_expr_effectful(kids[-1])

        if op_sp == "&":
            if not _is_lvalue(operand):
                raise NotImplementedError(f"address-of operand must be lvalue, got {type(operand).__name__}")
            return effects, AddrOf(ty=lower_type(cursor.type), expr=operand)
        if op_sp == "*":
            elem = getattr(getattr(operand, "ty", None), "elem", None)
            ty = elem if elem is not None else getattr(operand, "ty", Type.i32())
            return effects, Deref(ty=ty, expr=operand)
        if op_sp == "!":
            return effects, Binary(ty=Type.bool(), op=BinOp.EQ, lhs=operand, rhs=Literal(ty=operand.ty, value=0))
        if op_sp == "~":
            return effects, Binary(ty=operand.ty, op=BinOp.BIT_XOR, lhs=operand, rhs=Literal(ty=operand.ty, value=-1))
        if op_sp == "+":
            return effects, operand
        if op_sp == "-":
            ty = lower_type(cursor.type)
            return effects, Binary(ty=ty, op=BinOp.SUB, lhs=Literal(ty=ty, value=0), rhs=operand)

        raise NotImplementedError(f"Unsupported unary operator: {op_sp}")

    if cursor.kind == CursorKind.INIT_LIST_EXPR:
        effects: list[Stmt] = []
        elems: list[Expr] = []
        for c in cursor.get_children():
            if c.kind == CursorKind.TYPE_REF:
                continue
            if c.kind.is_expression() or c.kind in {CursorKind.UNEXPOSED_EXPR, CursorKind.PAREN_EXPR}:
                elem_effects, elem = lower_expr_effectful(c)
                effects.extend(elem_effects)
                elems.append(elem)
        return effects, InitList(ty=lower_type(cursor.type), elems=elems)

    if cursor.kind == CursorKind.CALL_EXPR:
        children = list(cursor.get_children())
        callee_effects, callee_ir = lower_expr_effectful(children[0])
        effects = list(callee_effects)
        args_ir: list[Expr] = []
        for arg in children[1:]:
            arg_effects, arg_ir = lower_expr_effectful(arg)
            effects.extend(arg_effects)
            args_ir.append(arg_ir)
        return effects, Call(ty=lower_type(cursor.type), callee=callee_ir, args=args_ir)

    if cursor.kind == CursorKind.MEMBER_REF_EXPR:
        kids = list(cursor.get_children())
        base_effects, base = lower_expr_effectful(kids[0])
        field_name = cursor.spelling or kids[-1].spelling
        is_arrow = _find_token(cursor, {"->"}) is not None
        ty = Type.i32()
        if is_arrow:
            return base_effects, Arrow(ty=ty, base=base, name=field_name)
        return base_effects, Field(ty=ty, base=base, name=field_name)

    return [], lower_expr(cursor)


def _lower_compound_assignment_parts(cursor: Cursor) -> tuple[Expr, Expr]:

    op_sp = _compound_op(cursor)
    if op_sp is None or op_sp not in COMPOUND_OPS:
        raise NotImplementedError(f"Unsupported compound assign operator: {op_sp}")

    lhs_cur, rhs_cur = list(cursor.get_children())
    lhs_ir = lower_expr(lhs_cur)

    if not _is_lvalue(lhs_ir):
        raise NotImplementedError(
            f"compound assign lhs must be lvalue, got {type(lhs_ir).__name__}"
        )

    rhs_ir = lower_expr(rhs_cur)
    bop = _binop_from_symbol(COMPOUND_OPS[op_sp])

    value = Binary(
        ty=lhs_ir.ty,
        op=bop,
        lhs=lhs_ir,
        rhs=rhs_ir,
    )

    return lhs_ir, value

def lower_expr(cursor: Cursor):
    
    if cursor.kind == CursorKind.COMPOUND_ASSIGNMENT_OPERATOR:
        target, value = _lower_compound_assignment_parts(cursor)
        return value
    

    if cursor.kind == CursorKind.INIT_LIST_EXPR:
        elems: list[Expr] = []
        for c in cursor.get_children():
            if c.kind == CursorKind.TYPE_REF:
                continue
            if c.kind.is_expression() or c.kind in {CursorKind.UNEXPOSED_EXPR, CursorKind.PAREN_EXPR}:
                elems.append(lower_expr(c))
        return InitList(ty=lower_type(cursor.type), elems=elems)
    if cursor.kind == CursorKind.UNARY_OPERATOR:
        inc_op = _unary_op(cursor)
        if inc_op in {"++", "--"}:
            effects, expr = lower_expr_effectful(cursor)
            if effects:
                # Pure expression lowering cannot represent statement effects;
                # callers that care about C side effects use lower_expr_effectful.
                return expr
            return expr

        op_sp = _unary_expr_op(cursor)
        kids = list(cursor.get_children())
        if not kids:
            raise NotImplementedError("UNARY_OPERATOR without operand")
        operand = lower_expr(kids[-1])

        if op_sp == "&":
            if not _is_lvalue(operand):
                raise NotImplementedError(f"address-of operand must be lvalue, got {type(operand).__name__}")
            return AddrOf(ty=lower_type(cursor.type), expr=operand)

        if op_sp == "*":
            elem = getattr(getattr(operand, "ty", None), "elem", None)
            ty = elem if elem is not None else getattr(operand, "ty", Type.i32())
            return Deref(ty=ty, expr=operand)

        if op_sp == "!":
            return Binary(ty=Type.bool(), op=BinOp.EQ, lhs=operand, rhs=Literal(ty=operand.ty, value=0))
        
        if op_sp == "~":
            return Binary(ty=operand.ty, op=BinOp.BIT_XOR, lhs=operand, rhs=Literal(ty=operand.ty, value=-1))
        
        if op_sp == "+":
            return operand

        if op_sp == "-":
            return Binary(
                ty=lower_type(cursor.type),
                op=BinOp.SUB,
                lhs=Literal(ty=lower_type(cursor.type), value=0),
                rhs=operand,
            )

        raise NotImplementedError(f"Unsupported unary operator: {op_sp}")

    if cursor.kind == CursorKind.ARRAY_SUBSCRIPT_EXPR:
        kids = list(cursor.get_children())
        if len(kids) != 2:
            raise NotImplementedError("ARRAY_SUBSCRIPT_EXPR without 2 children")
        base = lower_expr(kids[0])
        idx = lower_expr(kids[1])
        elem = getattr(getattr(base, "ty", None), "elem", None)
        ty = elem if elem is not None else Type.i32()
        return Index(ty=ty, base=base, index=idx)
    
    unwrap_kinds = {CursorKind.UNEXPOSED_EXPR, CursorKind.PAREN_EXPR}
    implicit_cast = getattr(CursorKind, "IMPLICIT_CAST_EXPR", None)
    if implicit_cast is not None:
        unwrap_kinds.add(implicit_cast)

    if cursor.kind in unwrap_kinds:
        children = list(cursor.get_children())
        if len(children) == 1:
            return lower_expr(children[0])
        if cursor.kind == CursorKind.UNEXPOSED_EXPR and len(children) == 0:
            for tok in cursor.get_tokens():
                s = tok.spelling
                if s and (s[0].isalpha() or s[0] == "_"):
                    return Var(name=s, ty=lower_type(cursor.type))
        raise NotImplementedError(f"unwrap node has unexpected children: {cursor.kind} len={len(children)}")

    if cursor.kind == CursorKind.INTEGER_LITERAL:
        tok = next(cursor.get_tokens())
        value = parse_c_int_literal(tok.spelling)
        ty = lower_type(cursor.type)
        if getattr(ty, "kind", None) == "int":
            if getattr(ty, "bits", None) == 32 and getattr(ty, "signed", None) is not None:
                if ty.signed.name == "SIGNED" and value > 2**31 - 1:
                    return Literal(ty=Type.u32(), value=value)
            return Literal(ty=ty, value=value)
        if value > 2**31 - 1:
            return Literal(ty=Type.u32(), value=value)
        else:
            return Literal(ty=Type.i32(), value=value)

    if cursor.kind == CursorKind.DECL_REF_EXPR:
        name = cursor.spelling
        return Var(name=name, ty=lower_type(cursor.type))

    if cursor.kind == CursorKind.BINARY_OPERATOR:
        kids = list(cursor.get_children())
        assert len(kids) == 2

        op_sp = _binary_operator_spelling(cursor)
        if op_sp == ",":
            return lower_expr(kids[1])

        if op_sp == "=":
            return lower_expr(kids[0])

        lhs = lower_expr(kids[0])
        rhs = lower_expr(kids[1])

        ir_op = _binop_from_symbol(op_sp)

        ty = Type.bool() if ir_op in _BOOL_RESULT else Type.i32()
        return Binary(ty=ty, op=ir_op, lhs=lhs, rhs=rhs)
    
    if cursor.kind == CursorKind.CALL_EXPR:
        children = list(cursor.get_children())
        callee = children[0]
        args = children[1:]
        callee_ir = lower_expr(callee) 
        args_ir = [lower_expr(a) for a in args]
        return Call(ty=lower_type(cursor.type), callee=callee_ir, args=args_ir)
    
    if cursor.kind == CursorKind.MEMBER_REF_EXPR:
        kids = list(cursor.get_children())
        base = lower_expr(kids[0])

        field_name = cursor.spelling or kids[-1].spelling

        is_arrow = _find_token(cursor, {"->"}) is not None

        ty = Type.i32()  
        if is_arrow:
            print("arrow")
            return Arrow(ty=ty, base=base, name=field_name)
        else:
            return Field(ty=ty, base=base, name=field_name)

    if cursor.kind == CursorKind.CSTYLE_CAST_EXPR:
        kids = list(cursor.get_children())
        kids = [k for k in kids if k.kind != CursorKind.TYPE_REF]
        if not kids:
            raise NotImplementedError("CSTYLE_CAST_EXPR without operand")
        expr = lower_expr(kids[-1])
        return Cast(to_ty=lower_type(cursor.type), expr=expr, ty=lower_type(cursor.type))

    raise NotImplementedError(cursor.kind)


def _has_compound_body(fn_cur: Cursor) -> bool:
    for c in fn_cur.get_children():
        if c.kind == CursorKind.COMPOUND_STMT:
            return True
    return False


def lower_struct_decl(cur: Cursor) -> StructDecl:
    assert cur.kind == CursorKind.STRUCT_DECL
    name = cur.spelling or (cur.type.spelling.replace("struct ", "").strip() if cur.type else "")
    fields: list[FieldDecl] = []
    for c in cur.get_children():
        if c.kind == CursorKind.FIELD_DECL:
            fields.append(FieldDecl(name=c.spelling, ty=lower_type(c.type)))
    return StructDecl(name=name, fields=fields)


def lower_global_var(cur: Cursor) -> GlobalVar:
    name = cur.spelling
    ty = lower_type(cur.type)
    init = _lower_vardecl_init(cur)

    return GlobalVar(name=name, ty=ty, init=init)


def lower_module(tu_cursor: Cursor) -> Module:
    decls: list[object] = []
    for c in tu_cursor.get_children():
        # struct definitions
        if c.kind == CursorKind.STRUCT_DECL and c.is_definition():
            decls.append(lower_struct_decl(c))
            continue

        # top-level globals
        if c.kind == CursorKind.VAR_DECL and c.semantic_parent and c.semantic_parent.kind == CursorKind.TRANSLATION_UNIT:
            decls.append(lower_global_var(c))
            continue

        # function definitions only (skip forward decls)
        if c.kind == CursorKind.FUNCTION_DECL and _has_compound_body(c):
            decls.append(lower_function(c))
            continue

    return Module(decls=decls)

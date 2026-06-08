from translator.ir.nodes import *
from translator.ir.types import Signedness, Type

def is_bool(ty):
    return ty.kind == "bool"


def is_i32(ty):
    return ty.kind == "int" and ty.bits == 32 and ty.signed == Signedness.SIGNED


def is_u32(ty):
    return ty.kind == "int" and ty.bits == 32 and ty.signed == Signedness.UNSIGNED


def is_i64(ty):
    return ty.kind == "int" and ty.bits == 64


def is_ptr(ty):
    return ty.kind == "ptr"



def cast_to(e: Expr, ty: Type) -> Expr:
    if e.ty == ty:
        return e
    return Cast(expr=e, to_ty=ty, ty=ty)


#cangjie does not support non-bool conditions, so we use !=0 instead
def ensure_bool(e: Expr) -> Expr:
    if is_bool(e.ty):
        return e
    return Binary(
        ty=Type.bool(),
        op=BinOp.NE,
        lhs=e,
        rhs=Literal(ty=e.ty, value=0),
    )

# in cangjie boolean values can't be cast to 1/0 directly, so we use a conditional expression to convert them
def bool_to_int(e: Expr) -> Expr:
    if not is_bool(e.ty):
        return e
    return Conditional(
        cond=e,
        then=Literal(ty=Type.i32(), value=1),
        else_=Literal(ty=Type.i32(), value=0),
        ty=Type.i32(),
    )


def wrap_int_value(value: int, ty: Type) -> int:
    bits = ty.bits
    if ty.kind != "int" or bits is None:
        return value

    mod = 1 << bits
    value = int(value) % mod
    if ty.signed == Signedness.SIGNED and value >= (1 << (bits - 1)):
        value -= mod
    return value


def coerce_expr_to_type(e: Expr, ty: Type) -> Expr:
    if ty.kind == "ptr":
        if e.ty.kind == "ptr":
            return e if e.ty == ty else Cast(expr=e, to_ty=ty, ty=ty)
        if isinstance(e, Literal) and int(e.value) == 0:
            return Cast(expr=e, to_ty=ty, ty=ty)
        return e
    if is_bool(e.ty) and ty.kind == "int":
        return coerce_expr_to_type(bool_to_int(e), ty)
    if ty.kind == "bool":
        return ensure_bool(e)
    if isinstance(e, Literal) and ty.kind == "int":
        return Literal(ty=ty, value=wrap_int_value(int(e.value), ty))
    if e.ty == ty:
        return e
    return cast_to(e, ty)


def normalize_init_list(e: InitList, ty: Type) -> InitList:
    if ty.kind == "array" and ty.elem is not None:
        elems = []
        for elem in e.elems:
            normalized = normalize_expr(elem)
            if isinstance(normalized, InitList):
                elems.append(normalize_init_list(normalized, ty.elem))
            else:
                elems.append(coerce_expr_to_type(normalized, ty.elem))
        return InitList(ty=ty, elems=elems)

    return InitList(
        ty=ty,
        elems=[normalize_expr(elem) for elem in e.elems],
    )


#算数统一
def unify_arith(lhs: Expr, rhs: Expr):
    lhs = bool_to_int(lhs)
    rhs = bool_to_int(rhs)

    if is_u32(lhs.ty) or is_u32(rhs.ty):
        lhs = cast_to(lhs, Type.u32())
        rhs = cast_to(rhs, Type.u32())
        return lhs, rhs

    lhs = cast_to(lhs, Type.i32())
    rhs = cast_to(rhs, Type.i32())
    return lhs, rhs


# ========= Expr=========
def normalize_expr(e: Expr) -> Expr:

    if isinstance(e, Binary):
        lhs = normalize_expr(e.lhs)
        rhs = normalize_expr(e.rhs)

        if e.op in {
            BinOp.LT, BinOp.LE, BinOp.GT, BinOp.GE,
            BinOp.EQ, BinOp.NE
        }:
            if is_ptr(lhs.ty) or is_ptr(rhs.ty):
                return Binary(Type.bool(), e.op, lhs, rhs)
            lhs, rhs = unify_arith(lhs, rhs)
            return Binary(Type.bool(), e.op, lhs, rhs)

        if e.op in {BinOp.LAND, BinOp.LOR}:
            lhs = ensure_bool(lhs)
            rhs = ensure_bool(rhs)
            return Binary(Type.bool(), e.op, lhs, rhs)

        lhs, rhs = unify_arith(lhs, rhs)
        return Binary(lhs.ty, e.op, lhs, rhs)

    if isinstance(e, Index):
        base = normalize_expr(e.base)
        idx = normalize_expr(e.index)
        return Index(e.ty, base, idx)

    if isinstance(e, AddrOf):
        return AddrOf(e.ty, normalize_expr(e.expr))

    if isinstance(e, Deref):
        return Deref(e.ty, normalize_expr(e.expr))

    if isinstance(e, Cast):
        inner = normalize_expr(e.expr)
        if is_bool(inner.ty) and e.to_ty.kind == "int":
            return bool_to_int(inner)
        return Cast(expr=inner, to_ty=e.to_ty, ty=e.ty)

    if isinstance(e, Call):
        return Call(
            ty=e.ty,
            callee=normalize_expr(e.callee),
            args=[normalize_expr(a) for a in e.args]
        )

    if isinstance(e, InitList):
        return normalize_init_list(e, e.ty)

    return e


# ========= Stmt =========

def normalize_stmt(s: Stmt, fn_ret_ty: Type | None = None) -> Stmt:

    if isinstance(s, Assign):
        target = normalize_expr(s.target)
        value = normalize_expr(s.value)
        return Assign(
            target=target,
            value=coerce_expr_to_type(value, target.ty)
        )

    if isinstance(s, Return):
        value = normalize_expr(s.value)
        if fn_ret_ty is not None:
            value = coerce_expr_to_type(value, fn_ret_ty)
        return Return(value)

    if isinstance(s, ExprStmt):
        return ExprStmt(normalize_expr(s.expr))

    if isinstance(s, If):
        cond = normalize_expr(s.cond)
        then_body = normalize_block(s.then_body, fn_ret_ty)
        else_body = normalize_block(s.else_body, fn_ret_ty) if s.else_body else None

        cond_bool = ensure_bool(cond)

        # Lower Conditional to If .eg: if(a?b:c)
        if isinstance(cond_bool, Conditional):
            c = cond_bool
            new_then = Block(then_body.stmts + (else_body.stmts if else_body else []))
            new_else = else_body if else_body else None
            return If(
                cond=c.cond,
                then_body=Block([
                    If(
                        cond=c.then,
                        then_body=then_body,
                        else_body=new_else
                    )
                ]),
                else_body=Block([
                    If(
                        cond=c.else_,
                        then_body=then_body,
                        else_body=new_else
                    )
                ])
            )
        else:
            return If(
                cond=cond_bool,
                then_body=then_body,
                else_body=else_body,
            )

    if isinstance(s, While):
        return While(
            cond=ensure_bool(normalize_expr(s.cond)),
            body=normalize_block(s.body, fn_ret_ty)
        )

    if isinstance(s, VarDecl):
        init = normalize_expr(s.init) if s.init else None
        if init is not None:
            init = coerce_expr_to_type(init, s.var.ty)
        return VarDecl(
            var=s.var,
            init=init
        )

    return s


# ========= Block =========

def normalize_block(b: Block, fn_ret_ty: Type | None = None) -> Block:
    return Block([normalize_stmt(s, fn_ret_ty) for s in b.stmts])


# ========= Function =========

def normalize_function(fn: Function) -> Function:
    return Function(
        name=fn.name,
        params=fn.params,
        ret_ty=fn.ret_ty,
        body=normalize_block(fn.body, fn.ret_ty)
    )


# ========= Module =========

def normalize_module(mod: Module) -> Module:
    new_decls = []
    for d in mod.decls:
        if isinstance(d, Function):
            new_decls.append(normalize_function(d))
        elif isinstance(d, GlobalVar):
            init = normalize_expr(d.init) if d.init else None
            if init is not None:
                init = coerce_expr_to_type(init, d.ty)
            new_decls.append(GlobalVar(name=d.name, ty=d.ty, init=init))
        else:
            new_decls.append(d)
    return Module(new_decls)

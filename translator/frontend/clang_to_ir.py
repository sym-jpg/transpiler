from clang.cindex import Cursor, CursorKind
from translator.ir.nodes import Literal, Var, Binary
from translator.ir.types import Type
from translator.ir.nodes import BinOp
from translator.ir.nodes import VarDecl, Assign, Return, Var
from translator.ir.nodes import Block, Function

def lower_function(cursor):
    assert cursor.kind == CursorKind.FUNCTION_DECL
    assert cursor.spelling == "main" 

    body = None
    for c in cursor.get_children():
        if c.kind == CursorKind.COMPOUND_STMT:
            stmts = []
            for s in c.get_children():
                stmts.append(lower_stmt(s))
            body = Block(stmts=stmts)

    assert body is not None

    return Function(
        name="main",
        params=[],
        ret_ty=Type.i32(),
        body=body,
    )

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
        children = list(cursor.get_children())
        lhs = lower_expr(children[0])
        rhs = lower_expr(children[1])

        return Binary(
            ty=Type.i32(),
            op=BinOp.ADD,
            lhs=lhs,
            rhs=rhs,
        )

    raise NotImplementedError(cursor.kind)

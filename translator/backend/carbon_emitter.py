from translator.ir.nodes import *
from translator.ir.types import Type
from translator.backend.ruleset import RuleSet

BIN_OP = {
  BinOp.ADD:"+", BinOp.SUB:"-", BinOp.MUL:"*", BinOp.DIV:"/",
  BinOp.LT:"<",  BinOp.LE:"<=", BinOp.GT:">",  BinOp.GE:">=",
  BinOp.EQ:"==", BinOp.NE:"!=",
  BinOp.LAND:"and", BinOp.LOR:"or",
}

UN_OP = { UnOp.NOT: "not" }

def emit_var(emitter, expr):
        return expr.name
    
def emit_binary(emitter, expr):
    return f"({emitter.emit_expr(expr.lhs)} {emitter.emit_op(expr.op)} {emitter.emit_expr(expr.rhs)})"

def emit_unary(emitter, expr):
    return f"({emitter.emit_unary_op(expr.op)} {emitter.emit_expr(expr.operand)})"

def emit_cast(emitter, expr):
    inner = emitter.emit_expr(expr.expr)
    return f"({inner}) as {emitter.emit_type(expr.to_ty)}"

def emit_literal(emitter, expr):
    if expr.ty.kind == "bool":
        return "true" if bool(expr.value) else "false"
    if expr.ty.kind == "int":
        return str(int(expr.value))
    if expr.ty.kind == "float":
        return str(float(expr.value))
    raise NotImplementedError(f"Literal type not supported: {expr.ty}")

def emit_vardecl(emitter, stmt, indent):
    pad = "  " * indent
    if stmt.init is None:
        return [f"{pad}var {stmt.var.name}: {emitter.emit_type(stmt.var.ty)};"]
    return [f"{pad}var {stmt.var.name}: {emitter.emit_type(stmt.var.ty)} = {emitter.emit_expr(stmt.init)};"]

def emit_assign(emitter, stmt, indent):
    pad = "  " * indent
    return [f"{pad}{stmt.target.name} = {emitter.emit_expr(stmt.value)};"]

def emit_return(emitter, stmt, indent):
    pad = "  " * indent
    return [f"{pad}return {emitter.emit_expr(stmt.value)};"]

def emit_while(emitter, stmt, indent):
    pad = "  " * indent
    lines = [f"{pad}while ({emitter.emit_expr(stmt.cond)}) {{"]
    lines += emitter.emit_block(stmt.body, indent + 1)
    lines.append(f"{pad}}}")
    return lines

def emit_if(emitter, stmt, indent):
    pad = "  " * indent
    lines = [f"{pad}if ({emitter.emit_expr(stmt.cond)}) {{"]
    lines += emitter.emit_block(stmt.then_body, indent + 1)
    if stmt.else_body is None:
        lines.append(f"{pad}}}")
        return lines
    lines.append(f"{pad}}} else {{")
    lines += emitter.emit_block(stmt.else_body, indent + 1)
    lines.append(f"{pad}}}")
    return lines

class CarbonEmitter:
    def __init__(self, rules: RuleSet):
        self.rules = rules
    
    def emit_function(self, fn: Function) -> str:
        params = ", ".join(
            f"{p.name}: {self.emit_type(p.ty)}" for p in fn.params
        )
        lines = [f"fn {fn.name}({params}) -> {self.emit_type(fn.ret_ty)} {{"]
        lines += self.emit_block(fn.body, indent=1)
        lines.append("}")
        return "\n".join(lines)
    
    def emit_block(self, block, indent):
        lines = []
        for stmt in block.stmts:
            fn = self.rules.stmt(stmt)
            lines += fn(self, stmt, indent)
        return lines

    def emit_expr(self, expr: Expr) -> str:
        try:
            fn = self.rules.expr(expr)
        except KeyError:
            raise NotImplementedError(f"No expr emitter for {type(expr).__name__}")
        return fn(self, expr)

    def emit_type(self, ty: Type) -> str:
        if ty.kind == "int" and ty.bits == 32:
            return "i32" if ty.signed.name == "SIGNED" else "u32"
        if ty.kind == "bool":
            return "bool"
        raise NotImplementedError(ty)
    
    def emit_op(self, op: BinOp) -> str:
        return BIN_OP[op]
    
    def emit_unary_op(self, op: UnOp) -> str:
        return UN_OP[op]


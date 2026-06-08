import json
import os
import re
from pathlib import Path

from translator.ir.nodes import *
from translator.ir.types import Signedness, Type
from translator.backend.ruleset import RuleSet

# Operator spelling differs by target language.
CARBON_BIN_OP = {
  BinOp.ADD: "+", BinOp.SUB: "-", BinOp.MUL: "*", BinOp.DIV: "/",
  BinOp.LT: "<",  BinOp.LE: "<=", BinOp.GT: ">",  BinOp.GE: ">=",
  BinOp.EQ: "==", BinOp.NE: "!=",
  BinOp.LAND: "and", BinOp.LOR: "or",
  BinOp.BIT_AND: "&", BinOp.BIT_OR: "|", BinOp.BIT_XOR: "^",
  BinOp.SHL: "<<", BinOp.SHR: ">>", BinOp.MOD: "%",
}

CARBON_UN_OP = { UnOp.NOT: "not" }

CANGJIE_BIN_OP = {
  BinOp.ADD: "+", BinOp.SUB: "-", BinOp.MUL: "*", BinOp.DIV: "/",
  BinOp.LT: "<",  BinOp.LE: "<=", BinOp.GT: ">",  BinOp.GE: ">=",
  BinOp.EQ: "==", BinOp.NE: "!=",
  BinOp.LAND: "&&", BinOp.LOR: "||",BinOp.BIT_AND: "&", BinOp.BIT_OR: "|", BinOp.BIT_XOR: "^", BinOp.SHL: "<<", BinOp.SHR: ">>", BinOp.MOD: "%",
}

CANGJIE_UN_OP = { UnOp.NOT: "!" }

def emit_var(emitter, expr):
    return expr.name

def emit_break(emitter, stmt, indent):
    pad = "  " * indent
    return [f"{pad}break{emitter.stmt_term}"]

def emit_continue(emitter, stmt, indent):
    pad = "  " * indent
    return [f"{pad}continue{emitter.stmt_term}"]

def emit_blockstmt(emitter, stmt: BlockStmt, indent: int) -> list[str]:
    lines: list[str] = []
    for s in stmt.block.stmts:
        fn = emitter.rules.stmt(s)
        lines += fn(emitter, s, indent)
    return lines

def emit_call_expr(emitter, expr: Call) -> str:
    def emit_any(x):
        if isinstance(x, Expr):
            return emitter.emit_expr(x)
        if isinstance(x, Var):
            return x.name
        return str(x)

    callee = emit_any(expr.callee)
    args = ", ".join(emit_any(a) for a in expr.args)
    return f"{callee}({args})"
    
def emit_binary(emitter, expr):
    return emitter.emit_binary_expr(expr)

# Support for Conditional node
def emit_conditional(emitter, expr: Conditional):
    return emitter.emit_conditional_expr(expr)

def emit_unary(emitter, expr):
    return f"({emitter.emit_unary_op(expr.op)} {emitter.emit_expr(expr.operand)})"

def emit_cast(emitter, expr):
    return emitter.emit_cast_expr(expr)

def emit_literal(emitter, expr):
    if expr.ty.kind == "bool":
        return "true" if bool(expr.value) else "false"
    if expr.ty.kind == "int":
        if isinstance(emitter, CarbonEmitter):
            return str(int(expr.value) & 0xFFFFFFFF) if expr.ty.bits == 32 and expr.ty.signed == Signedness.UNSIGNED else str(int(expr.value))
        if expr.ty.bits == 32 and expr.ty.signed == Signedness.UNSIGNED:
            return f"{int(expr.value) & 0xFFFFFFFF}u32"
        return str(int(expr.value))
    if expr.ty.kind == "float":
        return str(float(expr.value))
    raise NotImplementedError(f"Literal type not supported: {expr.ty}")

def default_init_expr(ty: Type) -> Expr:
    if ty.kind == "bool":
        return Literal(ty=ty, value=False)
    if ty.kind == "int":
        return Literal(ty=ty, value=0)
    if ty.kind == "float":
        return Literal(ty=ty, value=0.0)
    if ty.kind == "array":
        elem = ty.elem or Type.i32()
        n = ty.length or 0
        return InitList(ty=ty, elems=[default_init_expr(elem) for _ in range(n)])
    if ty.kind == "ptr":
        return Literal(ty=Type.i32(), value=0)
    raise NotImplementedError(f"No default initializer for type: {ty}")

def cangjie_c_helpers() -> str:
    return """func cInt32ToUInt32(x: Int32): UInt32 {
  return UInt32(Int64(x) & 0xFFFFFFFF)
}

func cUInt32ToInt32(x: UInt32): Int32 {
  if (x >= 0x80000000u32) {
    return Int32(Int64(x) - 0x100000000)
  }
  return Int32(x)
}

func cUInt32Add(x: UInt32, y: UInt32): UInt32 {
  return UInt32((UInt64(x) + UInt64(y)) & 0xFFFFFFFFu64)
}

func cUInt32Sub(x: UInt32, y: UInt32): UInt32 {
  return UInt32((Int64(x) - Int64(y)) & 0xFFFFFFFF)
}

func cUInt32Mul(x: UInt32, y: UInt32): UInt32 {
  return UInt32((UInt64(x) * UInt64(y)) & 0xFFFFFFFFu64)
}

func cInt32Add(x: Int32, y: Int32): Int32 {
  return cUInt32ToInt32(cUInt32Add(cInt32ToUInt32(x), cInt32ToUInt32(y)))
}

func cInt32Sub(x: Int32, y: Int32): Int32 {
  return cUInt32ToInt32(cUInt32Sub(cInt32ToUInt32(x), cInt32ToUInt32(y)))
}

func cInt32Mul(x: Int32, y: Int32): Int32 {
  return cUInt32ToInt32(cUInt32Mul(cInt32ToUInt32(x), cInt32ToUInt32(y)))
}

func cUInt32Div(x: UInt32, y: UInt32): UInt32 {
  if (y == 0u32) {
    return 0u32
  }
  return x / y
}

func cUInt32Mod(x: UInt32, y: UInt32): UInt32 {
  if (y == 0u32) {
    return 0u32
  }
  return x % y
}

func cInt32Div(x: Int32, y: Int32): Int32 {
  if (y == 0) {
    return 0
  }
  if ((x == -2147483648) && (y == -1)) {
    return -2147483648
  }
  return x / y
}

func cInt32Mod(x: Int32, y: Int32): Int32 {
  if (y == 0) {
    return 0
  }
  if ((x == -2147483648) && (y == -1)) {
    return 0
  }
  return x % y
}"""

def csmith_checksum_runtime() -> str:
    return cangjie_c_helpers() + "\n\n" + """var crc32Context: UInt32 = 0xFFFFFFFFu32
var crc32Tab: Array<UInt32> = Array<UInt32>(256, { _ => 0u32 })

func platformMainBegin(): Unit {
  crc32Context = 0xFFFFFFFFu32
}

func crc32Gentab(): Unit {
  let poly: UInt32 = 0xEDB88320u32
  var i: Int64 = 0

  while (i < 256) {
    var crc: UInt32 = UInt32(i)
    var j: Int64 = 8

    while (j > 0) {
      if ((crc & 1u32) != 0u32) {
        crc = ((crc >> 1) ^ poly) & 0xFFFFFFFFu32
      } else {
        crc = (crc >> 1) & 0xFFFFFFFFu32
      }
      j -= 1
    }

    crc32Tab[i] = crc
    i += 1
  }
}

func crc32Byte(b: UInt8): Unit {
  let idx: Int64 = Int64((crc32Context ^ UInt32(b)) & 0xFFu32)
  crc32Context = ((((crc32Context >> 8) & 0x00FFFFFFu32) ^ crc32Tab[idx]) & 0xFFFFFFFFu32)
}

func crc32_8bytes(val: UInt64): Unit {
  crc32Byte(UInt8((val >> 0) & 0xFFu64))
  crc32Byte(UInt8((val >> 8) & 0xFFu64))
  crc32Byte(UInt8((val >> 16) & 0xFFu64))
  crc32Byte(UInt8((val >> 24) & 0xFFu64))
  crc32Byte(UInt8((val >> 32) & 0xFFu64))
  crc32Byte(UInt8((val >> 40) & 0xFFu64))
  crc32Byte(UInt8((val >> 48) & 0xFFu64))
  crc32Byte(UInt8((val >> 56) & 0xFFu64))
}

func crcValueInt32(x: Int32): UInt64 {
  if (x < 0) {
    return 0xFFFFFFFF00000000u64 | UInt64(Int64(x) & 0xFFFFFFFF)
  }
  return UInt64(x)
}

func hexDigit(x: UInt32): String {
  if (x == 0u32) { return "0" }
  if (x == 1u32) { return "1" }
  if (x == 2u32) { return "2" }
  if (x == 3u32) { return "3" }
  if (x == 4u32) { return "4" }
  if (x == 5u32) { return "5" }
  if (x == 6u32) { return "6" }
  if (x == 7u32) { return "7" }
  if (x == 8u32) { return "8" }
  if (x == 9u32) { return "9" }
  if (x == 10u32) { return "A" }
  if (x == 11u32) { return "B" }
  if (x == 12u32) { return "C" }
  if (x == 13u32) { return "D" }
  if (x == 14u32) { return "E" }
  return "F"
}

func uint32Hex(x: UInt32): String {
  return hexDigit((x >> 28) & 0xFu32) +
    hexDigit((x >> 24) & 0xFu32) +
    hexDigit((x >> 20) & 0xFu32) +
    hexDigit((x >> 16) & 0xFu32) +
    hexDigit((x >> 12) & 0xFu32) +
    hexDigit((x >> 8) & 0xFu32) +
    hexDigit((x >> 4) & 0xFu32) +
    hexDigit(x & 0xFu32)
}

func transparentCrc(val: UInt64, vname: String, flag: Int64): Unit {
  crc32_8bytes(val)
  if (flag != 0) {
    println("after hashing " + vname + ": " + uint32Hex(crc32Context ^ 0xFFFFFFFFu32))
  }
}

func finalChecksum(): UInt32 {
  return (crc32Context ^ 0xFFFFFFFFu32) & 0xFFFFFFFFu32
}

func platformMainEnd(crc: UInt32, flag: Int64): Unit {
  println("checksum = " + uint32Hex(crc))
}"""

def emit_vardecl(emitter, stmt, indent):
    return emitter.emit_vardecl_stmt(stmt, indent)

def emit_assign(emitter, stmt, indent):
    return emitter.emit_assign_stmt(stmt, indent)

def emit_return(emitter, stmt, indent):
    pad = "  " * indent
    return [f"{pad}return {emitter.emit_expr(stmt.value)}{emitter.stmt_term}"]

def emit_while(emitter, stmt, indent):
    return emitter.emit_while_stmt(stmt, indent)

def emit_if(emitter, stmt, indent):
    return emitter.emit_if_stmt(stmt, indent)

def emit_exprstmt(emitter, stmt: ExprStmt, indent: int) -> list[str]:
    pad = "  " * indent
    return [f"{pad}{emitter.emit_expr(stmt.expr)}{emitter.stmt_term}"]

class BaseEmitter:

    # Concrete emitters should override these.
    fn_kw: str = "fn"
    fn_ret_sep: str = "->"  # how to spell return type separator
    stmt_term: str = ";"     # statement terminator (";" for Carbon, "" for Cangjie)
    bin_op_map = CARBON_BIN_OP
    un_op_map = CARBON_UN_OP

    def __init__(self, rules: RuleSet):
        self.rules = rules
        self._tmp_counter = 0

    def emit_function(self, fn: Function) -> str:
        params = ", ".join(f"{p.name}: {self.emit_type(p.ty)}" for p in fn.params)
        header = f"{self.fn_kw} {fn.name}({params}) {self.fn_ret_sep} {self.emit_type(fn.ret_ty)} {{"
        lines = [header]
        lines += self.emit_block(fn.body, indent=1)
        lines.append("}")
        return "\n".join(lines)

    def emit_global_var(self, gv: GlobalVar) -> str:
        """Emit a file-scope global variable using the same VarDecl rule as locals."""
        stmt = VarDecl(var=Var(name=gv.name, ty=gv.ty), init=gv.init)
        fn = self.rules.stmt(stmt)
        return "\n".join(fn(self, stmt, 0))

    def emit_struct_decl(self, st: StructDecl) -> str:
        name = st.name
        lines = [f"struct {name} {{"]
        for field in st.fields:
            lines.append(f"  var {field.name}: {self.emit_type(field.ty)}")
        lines.append("}")
        return "\n".join(lines)

    def emit_module(self, module) -> str:
        """Emit a complete module lowered by lower_module(...)."""
        parts: list[str] = []

        decls = getattr(module, "decls", None)
        if decls is not None:
            for decl in decls:
                if isinstance(decl, StructDecl):
                    parts.append(self.emit_struct_decl(decl))
                elif isinstance(decl, GlobalVar):
                    parts.append(self.emit_global_var(decl))
                elif isinstance(decl, Function):
                    parts.append(self.emit_function(decl))
                else:
                    raise NotImplementedError(f"Unsupported module decl: {type(decl).__name__}")
        else:
            for st in getattr(module, "structs", []):
                parts.append(self.emit_struct_decl(st))
            for gv in getattr(module, "globals", getattr(module, "global_vars", [])):
                parts.append(self.emit_global_var(gv))
            for fn in getattr(module, "functions", []):
                parts.append(self.emit_function(fn))

        return "\n\n".join(p for p in parts if p.strip()) + "\n"

    def emit_block(self, block, indent: int) -> list[str]:
        lines: list[str] = []
        for stmt in block.stmts:
            fn = self.rules.stmt(stmt)
            lines += fn(self, stmt, indent)
        return lines

    def emit_expr(self, expr: Expr) -> str:
        # Add support for Conditional node in generic expr dispatch
        if isinstance(expr, Conditional):
            return emit_conditional(self, expr)
        try:
            fn = self.rules.expr(expr)
        except KeyError:
            raise NotImplementedError(f"No expr emitter for {type(expr).__name__}")
        return fn(self, expr)

    def emit_binary_expr(self, expr: Binary) -> str:
        lhs = self.emit_expr(expr.lhs)
        rhs = self.emit_expr(expr.rhs)
        return f"({lhs} {self.emit_op(expr.op)} {rhs})"

    def emit_conditional_expr(self, expr: Conditional) -> str:
        cond = self.emit_expr(expr.cond)
        then = self.emit_expr(expr.then)
        else_ = self.emit_expr(expr.else_)
        return f"(({cond}) ? ({then}) : ({else_}))"

    def emit_cast_expr(self, expr: Cast) -> str:
        inner = self.emit_expr(expr.expr)
        return f"({inner}) as {self.emit_type(expr.to_ty)}"

    def emit_vardecl_stmt(self, stmt: VarDecl, indent: int) -> list[str]:
        pad = "  " * indent
        if stmt.init is None:
            init = default_init_expr(stmt.var.ty)
            return [f"{pad}var {stmt.var.name}: {self.emit_type(stmt.var.ty)} = {self.emit_expr(init)}{self.stmt_term}"]
        return [f"{pad}var {stmt.var.name}: {self.emit_type(stmt.var.ty)} = {self.emit_expr(stmt.init)}{self.stmt_term}"]

    def emit_assign_stmt(self, stmt: Assign, indent: int) -> list[str]:
        pad = "  " * indent
        tgt = stmt.target
        rhs = self.emit_expr(stmt.value)

        if isinstance(tgt, Deref):
            p = self.emit_expr(tgt.expr)
            return [f"{pad}unsafe {{ {p}.write({rhs}) }}{self.stmt_term}"]

        if isinstance(tgt, Index):
            nested = self.emit_index_assign(tgt, rhs, indent)
            if nested is not None:
                return nested
            base = self.emit_expr(tgt.base)
            idx = f"Int64({self.emit_expr(tgt.index)})"
            return [f"{pad}{base}[{idx}] = {rhs}{self.stmt_term}"]

        lhs = self.emit_expr(tgt)
        return [f"{pad}{lhs} = {rhs}{self.stmt_term}"]

    def emit_while_stmt(self, stmt: While, indent: int) -> list[str]:
        pad = "  " * indent
        cond = self.emit_condition(stmt.cond)
        lines = [f"{pad}while ({cond}) {{"]
        lines += self.emit_block(stmt.body, indent + 1)
        lines.append(f"{pad}}}")
        return lines

    def emit_if_stmt(self, stmt: If, indent: int) -> list[str]:
        pad = "  " * indent
        cond = self.emit_condition(stmt.cond)
        lines = [f"{pad}if ({cond}) {{"]
        lines += self.emit_block(stmt.then_body, indent + 1)
        if stmt.else_body is None:
            lines.append(f"{pad}}}")
            return lines
        lines.append(f"{pad}}} else {{")
        lines += self.emit_block(stmt.else_body, indent + 1)
        lines.append(f"{pad}}}")
        return lines

    def fresh_tmp(self) -> str:
        name = f"__cj_tmp_{self._tmp_counter}"
        self._tmp_counter += 1
        return name

    def emit_index_assign(self, target: Index, rhs: str, indent: int) -> list[str] | None:
        chain: list[Index] = []
        cur = target
        while isinstance(cur, Index):
            chain.append(cur)
            cur = cur.base
        chain.reverse()

        if len(chain) <= 1:
            return None

        pad = "  " * indent
        root = self.emit_expr(chain[0].base)
        indices = [f"Int64({self.emit_expr(item.index)})" for item in chain]
        temps = [self.fresh_tmp() for _ in range(len(indices) - 1)]

        lines: list[str] = []
        lines.append(f"{pad}var {temps[0]} = {root}[{indices[0]}]{self.stmt_term}")
        for i in range(1, len(temps)):
            lines.append(f"{pad}var {temps[i]} = {temps[i - 1]}[{indices[i]}]{self.stmt_term}")

        holder = temps[-1]
        lines.append(f"{pad}{holder}[{indices[-1]}] = {rhs}{self.stmt_term}")

        for i in range(len(temps) - 2, -1, -1):
            child = temps[i + 1]
            lines.append(f"{pad}{temps[i]}[{indices[i + 1]}] = {child}{self.stmt_term}")

        lines.append(f"{pad}{root}[{indices[0]}] = {temps[0]}{self.stmt_term}")
        return lines
    
    def emit_condition(self, expr) -> str:
        text = self.emit_expr(expr)
        ty = getattr(expr, "ty", None)
        is_bool = getattr(ty, "kind", None) == "bool"
        if is_bool:
            return text
        return f"({text} != 0)"

    def emit_type(self, ty: Type) -> str:
        raise NotImplementedError("Concrete emitter must implement emit_type")

    def emit_op(self, op: BinOp) -> str:
        return self.bin_op_map[op]

    def emit_unary_op(self, op: UnOp) -> str:
        return self.un_op_map[op]


class CarbonEmitter(BaseEmitter):
    fn_kw = "fn"
    fn_ret_sep = "->"
    stmt_term = ";"
    bin_op_map = CARBON_BIN_OP
    un_op_map = CARBON_UN_OP

    def emit_type(self, ty: Type) -> str:
        if ty.kind == "int" and ty.bits == 32:
            return "i32" if ty.signed.name == "SIGNED" else "u32"
        if ty.kind == "bool":
            return "bool"
        if ty.kind == "void":
            return "()"
        raise NotImplementedError(ty)

    def emit_conditional_expr(self, expr: Conditional) -> str:
        cond = self.emit_expr(expr.cond)
        then = self.emit_expr(expr.then)
        else_ = self.emit_expr(expr.else_)
        return f"(if ({cond}) then {then} else {else_})"

    def _format_int_constant(self, value: int, ty: Type) -> str:
        bits = ty.bits
        if bits is None:
            return str(value)
        mod = 1 << bits
        value %= mod
        if ty.signed == Signedness.SIGNED and value >= (1 << (bits - 1)):
            value -= mod
        return str(value)

    def _eval_int_constant(self, expr: Expr) -> int | None:
        if isinstance(expr, Literal) and getattr(expr.ty, "kind", None) == "int":
            return int(expr.value)
        if isinstance(expr, Cast):
            value = self._eval_int_constant(expr.expr)
            if value is None or getattr(expr.to_ty, "kind", None) != "int":
                return None
            bits = expr.to_ty.bits
            if bits is None:
                return value
            mod = 1 << bits
            value %= mod
            if expr.to_ty.signed == Signedness.SIGNED and value >= (1 << (bits - 1)):
                value -= mod
            return value
        if isinstance(expr, Binary):
            lhs = self._eval_int_constant(expr.lhs)
            rhs = self._eval_int_constant(expr.rhs)
            if lhs is None or rhs is None:
                return None
            if expr.op == BinOp.ADD:
                return lhs + rhs
            if expr.op == BinOp.SUB:
                return lhs - rhs
            if expr.op == BinOp.MUL:
                return lhs * rhs
            if expr.op == BinOp.BIT_AND:
                return lhs & rhs
            if expr.op == BinOp.BIT_OR:
                return lhs | rhs
            if expr.op == BinOp.BIT_XOR:
                return lhs ^ rhs
            if expr.op == BinOp.SHL and 0 <= rhs < 64:
                return lhs << rhs
            if expr.op == BinOp.SHR and 0 <= rhs < 64:
                return lhs >> rhs
            if expr.op == BinOp.DIV and rhs != 0:
                return int(lhs / rhs)
            if expr.op == BinOp.MOD and rhs != 0:
                return lhs % rhs
        return None

    def emit_binary_expr(self, expr: Binary) -> str:
        if getattr(expr.ty, "kind", None) == "int":
            value = self._eval_int_constant(expr)
            if value is not None:
                return self._format_int_constant(value, expr.ty)
        return super().emit_binary_expr(expr)

    def emit_cast_expr(self, expr: Cast) -> str:
        if expr.to_ty.kind == "int" and expr.to_ty.bits == 32:
            value = self._eval_int_constant(expr.expr)
            if value is not None:
                return self._format_int_constant(value, expr.to_ty)
        inner = self.emit_expr(expr.expr)
        return f"(({inner}) as {self.emit_type(expr.to_ty)})"


class CangjieEmitter(BaseEmitter):
    fn_kw = "func"
    fn_ret_sep = ":"  
    stmt_term = ""    
    bin_op_map = CANGJIE_BIN_OP
    un_op_map = CANGJIE_UN_OP
    _PTR_UNKNOWN = object()

    def __init__(self, rules: RuleSet):
        super().__init__(rules)
        self._global_ptr_aliases: dict[str, Expr | None | object] = {}
        self._ptr_aliases: dict[str, Expr | None | object] = self._global_ptr_aliases
        self._global_ptr_arrays: dict[str, object] = {}
        self._ptr_arrays: dict[str, object] = self._global_ptr_arrays
        self._emitting_global = False

    def emit_binary_expr(self, expr: Binary) -> str:
        if self.is_pointer_expr(expr.lhs) or self.is_pointer_expr(expr.rhs):
            return self.emit_pointer_binary(expr)

        lhs = self.emit_expr(expr.lhs)
        rhs = self.emit_expr(expr.rhs)

        if expr.op == BinOp.ADD:
            if getattr(expr.ty, "kind", None) == "int" and getattr(expr.ty, "signed", None) == Signedness.UNSIGNED:
                return f"cUInt32Add({lhs}, {rhs})"
            if getattr(expr.ty, "kind", None) == "int":
                return f"cInt32Add({lhs}, {rhs})"
        if expr.op == BinOp.SUB:
            if getattr(expr.ty, "kind", None) == "int" and getattr(expr.ty, "signed", None) == Signedness.UNSIGNED:
                return f"cUInt32Sub({lhs}, {rhs})"
            if getattr(expr.ty, "kind", None) == "int":
                return f"cInt32Sub({lhs}, {rhs})"
        if expr.op == BinOp.MUL:
            if getattr(expr.ty, "kind", None) == "int" and getattr(expr.ty, "signed", None) == Signedness.UNSIGNED:
                return f"cUInt32Mul({lhs}, {rhs})"
            if getattr(expr.ty, "kind", None) == "int":
                return f"cInt32Mul({lhs}, {rhs})"
        if expr.op == BinOp.DIV:
            if getattr(expr.ty, "kind", None) == "int" and getattr(expr.ty, "signed", None) == Signedness.UNSIGNED:
                return f"cUInt32Div({lhs}, {rhs})"
            return f"cInt32Div({lhs}, {rhs})"
        if expr.op == BinOp.MOD:
            if getattr(expr.ty, "kind", None) == "int" and getattr(expr.ty, "signed", None) == Signedness.UNSIGNED:
                return f"cUInt32Mod({lhs}, {rhs})"
            return f"cInt32Mod({lhs}, {rhs})"

        return f"({lhs} {self.emit_op(expr.op)} {rhs})"

    def emit_conditional_expr(self, expr: Conditional) -> str:
        cond = self.emit_expr(expr.cond)
        then = self.emit_expr(expr.then)
        else_ = self.emit_expr(expr.else_)
        return f"(if ({cond}) {{ {then} }} else {{ {else_} }})"

    def emit_cast_expr(self, expr: Cast) -> str:
        inner = self.emit_expr(expr.expr)
        if expr.to_ty.kind in {"int", "float"}:
            from_ty = getattr(expr.expr, "ty", None)
            if (
                expr.to_ty.kind == "int"
                and expr.to_ty.bits == 32
                and expr.to_ty.signed == Signedness.UNSIGNED
                and getattr(from_ty, "kind", None) == "int"
                and getattr(from_ty, "bits", None) == 32
                and getattr(from_ty, "signed", None) == Signedness.SIGNED
            ):
                return f"cInt32ToUInt32({inner})"
            if (
                expr.to_ty.kind == "int"
                and expr.to_ty.bits == 32
                and expr.to_ty.signed == Signedness.SIGNED
                and getattr(from_ty, "kind", None) == "int"
                and getattr(from_ty, "bits", None) == 32
                and getattr(from_ty, "signed", None) == Signedness.UNSIGNED
            ):
                return f"cUInt32ToInt32({inner})"
            return f"{self.emit_type(expr.to_ty)}({inner})"
        return super().emit_cast_expr(expr)

    def emit_vardecl_stmt(self, stmt: VarDecl, indent: int) -> list[str]:
        if self.is_pointer_type(stmt.var.ty):
            self.declare_pointer(stmt.var.name, stmt.init)
            return []
        if self.contains_pointer_type(stmt.var.ty):
            self.declare_pointer_array(stmt.var.name, stmt.init)
            return []
        return super().emit_vardecl_stmt(stmt, indent)

    def emit_assign_stmt(self, stmt: Assign, indent: int) -> list[str]:
        pad = "  " * indent
        tgt = stmt.target

        if isinstance(tgt, Var) and self.is_pointer_type(tgt.ty):
            self.assign_pointer(tgt.name, stmt.value)
            return []

        if isinstance(tgt, Index) and self.is_pointer_type(tgt.ty):
            return []

        rhs = self.emit_expr(stmt.value)

        if isinstance(tgt, Deref):
            resolved = self.resolve_deref_target(tgt)
            nested = self.emit_index_assign(resolved, rhs, indent) if isinstance(resolved, Index) else None
            if nested is not None:
                return nested
            return [f"{pad}{self.emit_expr(resolved)} = {rhs}{self.stmt_term}"]

        if isinstance(tgt, Index):
            nested = self.emit_index_assign(tgt, rhs, indent)
            if nested is not None:
                return nested
            base = self.emit_expr(tgt.base)
            idx = f"Int64({self.emit_expr(tgt.index)})"
            return [f"{pad}{base}[{idx}] = {rhs}{self.stmt_term}"]

        lhs = self.emit_expr(tgt)
        return [f"{pad}{lhs} = {rhs}{self.stmt_term}"]

    def emit_while_stmt(self, stmt: While, indent: int) -> list[str]:
        pad = "  " * indent
        cond = self.emit_condition(stmt.cond)
        lines = [f"{pad}while ({cond}) {{"]
        before = self.copy_pointer_aliases()
        self.set_pointer_aliases(before)
        lines += self.emit_block(stmt.body, indent + 1)
        after_body = self.copy_pointer_aliases()
        self.set_pointer_aliases(before)
        self.mark_loop_pointer_changes(after_body)
        lines.append(f"{pad}}}")
        return lines

    def emit_if_stmt(self, stmt: If, indent: int) -> list[str]:
        pad = "  " * indent
        cond = self.emit_condition(stmt.cond)
        lines = [f"{pad}if ({cond}) {{"]

        before = self.copy_pointer_aliases()
        self.set_pointer_aliases(before)
        lines += self.emit_block(stmt.then_body, indent + 1)
        then_aliases = self.copy_pointer_aliases()
        self.set_pointer_aliases(before)

        if stmt.else_body is None:
            lines.append(f"{pad}}}")
            self.merge_pointer_aliases(then_aliases, before)
            return lines

        lines.append(f"{pad}}} else {{")
        self.set_pointer_aliases(before)
        lines += self.emit_block(stmt.else_body, indent + 1)
        else_aliases = self.copy_pointer_aliases()
        self.merge_pointer_aliases(then_aliases, else_aliases)
        lines.append(f"{pad}}}")
        return lines

    def is_pointer_type(self, ty: Type | None) -> bool:
        return getattr(ty, "kind", None) == "ptr"

    def contains_pointer_type(self, ty: Type | None) -> bool:
        cur = ty
        while cur is not None and getattr(cur, "kind", None) == "array":
            cur = cur.elem
        return self.is_pointer_type(cur)

    def is_pointer_expr(self, expr: Expr) -> bool:
        return self.is_pointer_type(getattr(expr, "ty", None))

    def _target_key(self, target: Expr | None | object) -> str:
        if target is None:
            return "<null>"
        if target is self._PTR_UNKNOWN:
            return "<unknown>"
        return repr(target)

    def copy_pointer_aliases(self) -> dict[str, Expr | None | object]:
        return dict(self._ptr_aliases)

    def set_pointer_aliases(self, aliases: dict[str, Expr | None | object]) -> None:
        self._ptr_aliases = dict(aliases)

    def merge_pointer_aliases(
        self,
        lhs: dict[str, Expr | None | object] | None,
        rhs: dict[str, Expr | None | object] | None,
    ) -> None:
        lhs = lhs or {}
        rhs = rhs or {}
        merged: dict[str, Expr | None | object] = {}
        for name in set(lhs) | set(rhs):
            lval = lhs.get(name, self._PTR_UNKNOWN)
            rval = rhs.get(name, self._PTR_UNKNOWN)
            merged[name] = lval if self._target_key(lval) == self._target_key(rval) else self._PTR_UNKNOWN
        self._ptr_aliases = merged

    def mark_loop_pointer_changes(self, after_body: dict[str, Expr | None | object]) -> None:
        for name, target in after_body.items():
            if self._target_key(self._ptr_aliases.get(name, self._PTR_UNKNOWN)) != self._target_key(target):
                self._ptr_aliases[name] = self._PTR_UNKNOWN

    def _is_null_pointer_expr(self, expr: Expr) -> bool:
        if isinstance(expr, Literal):
            try:
                return int(expr.value) == 0
            except Exception:
                return False
        if isinstance(expr, Cast):
            return self.is_pointer_type(expr.to_ty) and self._is_null_pointer_expr(expr.expr)
        return False

    def _literal_index(self, expr: Expr) -> int | None:
        if isinstance(expr, Literal):
            try:
                return int(expr.value)
            except Exception:
                return None
        if isinstance(expr, Cast):
            return self._literal_index(expr.expr)
        return None

    def _pointer_array_from_init(self, init: Expr | None) -> object:
        if init is None:
            return self._PTR_UNKNOWN
        if isinstance(init, InitList):
            return [self._pointer_array_from_init(item) for item in init.elems]
        return self.resolve_pointer_value(init)

    def _same_pointer_array_leaf(self, value: object) -> Expr | None | object:
        if isinstance(value, list):
            leaf = self._PTR_UNKNOWN
            have_leaf = False
            for item in value:
                cur = self._same_pointer_array_leaf(item)
                if cur is self._PTR_UNKNOWN:
                    return self._PTR_UNKNOWN
                if not have_leaf:
                    leaf = cur
                    have_leaf = True
                elif self._target_key(leaf) != self._target_key(cur):
                    return self._PTR_UNKNOWN
            return leaf if have_leaf else self._PTR_UNKNOWN
        return value

    def _index_chain(self, expr: Index) -> tuple[Expr, list[Expr]]:
        indices: list[Expr] = []
        cur: Expr = expr
        while isinstance(cur, Index):
            indices.append(cur.index)
            cur = cur.base
        indices.reverse()
        return cur, indices

    def declare_pointer_array(self, name: str, init: Expr | None) -> None:
        self._ptr_arrays[name] = self._pointer_array_from_init(init)

    def resolve_pointer_array_value(self, expr: Index) -> Expr | None | object:
        root, indices = self._index_chain(expr)
        if not isinstance(root, Var):
            return self._PTR_UNKNOWN
        value = self._ptr_arrays.get(root.name, self._PTR_UNKNOWN)
        for idx_expr in indices:
            if not isinstance(value, list):
                return value
            idx = self._literal_index(idx_expr)
            if idx is None:
                return self._same_pointer_array_leaf(value)
            if idx < 0 or idx >= len(value):
                return self._PTR_UNKNOWN
            value = value[idx]
        return value

    def resolve_pointer_value(self, expr: Expr) -> Expr | None | object:
        if isinstance(expr, AddrOf):
            return expr.expr
        if isinstance(expr, Var) and self.is_pointer_type(expr.ty):
            return self._ptr_aliases.get(expr.name, self._PTR_UNKNOWN)
        if isinstance(expr, Index) and self.is_pointer_type(expr.ty):
            return self.resolve_pointer_array_value(expr)
        if isinstance(expr, Cast):
            if self._is_null_pointer_expr(expr):
                return None
            return self.resolve_pointer_value(expr.expr)
        if self._is_null_pointer_expr(expr):
            return None
        if self.is_pointer_expr(expr):
            raise NotImplementedError(f"Unsupported pointer expression: {type(expr).__name__}")
        raise NotImplementedError(f"Expression is not a pointer: {type(expr).__name__}")

    def declare_pointer(self, name: str, init: Expr | None) -> None:
        if init is None:
            self._ptr_aliases[name] = None if self._emitting_global else self._PTR_UNKNOWN
            return
        self._ptr_aliases[name] = self.resolve_pointer_value(init)

    def assign_pointer(self, name: str, value: Expr) -> None:
        self._ptr_aliases[name] = self.resolve_pointer_value(value)

    def resolve_deref_target(self, expr: Deref) -> Expr:
        target = self.resolve_pointer_value(expr.expr)
        if target is None:
            raise NotImplementedError("Null pointer dereference is unsupported")
        if target is self._PTR_UNKNOWN:
            raise NotImplementedError("Pointer target is not statically known")
        if not isinstance(target, Expr):
            raise NotImplementedError(f"Unsupported pointer target: {target!r}")
        return target

    def emit_pointer_binary(self, expr: Binary) -> str:
        if expr.op not in {BinOp.EQ, BinOp.NE}:
            raise NotImplementedError(f"Unsupported pointer operator: {expr.op}")
        lhs = self.resolve_pointer_value(expr.lhs)
        rhs = self.resolve_pointer_value(expr.rhs)
        if lhs is self._PTR_UNKNOWN or rhs is self._PTR_UNKNOWN:
            raise NotImplementedError("Pointer comparison with unknown target is unsupported")
        same = self._target_key(lhs) == self._target_key(rhs)
        value = same if expr.op == BinOp.EQ else not same
        return "true" if value else "false"

    def emit_expr(self, expr: Expr) -> str:
        if isinstance(expr, AddrOf):
            raise NotImplementedError("Address-of must be consumed by pointer lowering before Cangjie emission")
        if isinstance(expr, Deref):
            return self.emit_expr(self.resolve_deref_target(expr))
        if isinstance(expr, Index) and self.is_pointer_type(expr.ty):
            raise NotImplementedError("Pointer array element cannot be emitted directly")
        if isinstance(expr, Var) and self.is_pointer_type(expr.ty):
            raise NotImplementedError(f"Pointer variable {expr.name} cannot be emitted directly")
        return super().emit_expr(expr)

    def _load_checksum_vars(self) -> list[tuple[str, str]]:
        configured = os.environ.get("CHECKSUM_VARS_JSON")
        if not configured:
            return []
        path = Path(configured)
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        out: list[tuple[str, str]] = []
        for item in payload.get("checksum_vars", []):
            if isinstance(item, list) and len(item) >= 2:
                out.append((str(item[0]), str(item[1])))
        return out

    def _parse_checksum_ref(self, ref: str) -> tuple[str, list[str]]:
        m = re.match(r"^\s*([A-Za-z_]\w*)((?:\s*\[[^\]]+\])*)\s*$", ref)
        if m is None:
            return ref.strip(), []
        indices = re.findall(r"\[\s*([^\]]+)\s*\]", m.group(2))
        return m.group(1), indices

    def _array_dims(self, ty: Type | None) -> list[int]:
        dims: list[int] = []
        cur = ty
        while cur is not None and cur.kind == "array":
            if cur.length is None:
                break
            dims.append(int(cur.length))
            cur = cur.elem
        return dims

    def _array_elem_ty(self, ty: Type | None) -> Type | None:
        cur = ty
        while cur is not None and cur.kind == "array":
            cur = cur.elem
        return cur

    def _checksum_value_arg(self, expr: str, ty: Type | None) -> str:
        if ty is not None and ty.kind == "int" and ty.bits == 32:
            if ty.signed == Signedness.SIGNED:
                return f"crcValueInt32({expr})"
            return f"UInt64({expr})"
        if ty is not None and ty.kind == "bool":
            return f"UInt64((if ({expr}) {{ 1 }} else {{ 0 }}))"
        return f"UInt64({expr})"

    def _checksum_arg(self, ref: str, globals_by_name: dict[str, GlobalVar]) -> str:
        base, indices = self._parse_checksum_ref(ref)
        gv = globals_by_name.get(base)
        ty = getattr(gv, "ty", None)
        elem_ty = self._array_elem_ty(ty) if indices else ty
        expr = base + "".join(f"[{idx}]" for idx in indices)
        return self._checksum_value_arg(expr, elem_ty)

    def _emit_checksum_item(
        self,
        ref: str,
        display_name: str,
        globals_by_name: dict[str, GlobalVar],
        item_index: int,
    ) -> list[str]:
        base, indices = self._parse_checksum_ref(ref)
        gv = globals_by_name.get(base)
        ty = getattr(gv, "ty", None)
        dims = self._array_dims(ty)

        if not indices:
            arg = self._checksum_arg(ref, globals_by_name)
            return [f"  transparentCrc({arg}, \"{display_name}\", printHashValue)"]

        if not dims:
            arg = self._checksum_arg(ref, globals_by_name)
            return [f"  transparentCrc({arg}, \"{display_name}\", printHashValue)"]

        loop_count = min(len(indices), len(dims))
        loop_vars = [f"__ck_{item_index}_{i}" for i in range(loop_count)]
        expr = base + "".join(f"[{v}]" for v in loop_vars)
        elem_ty = self._array_elem_ty(ty)
        arg = self._checksum_value_arg(expr, elem_ty)

        lines: list[str] = []
        for depth, (loop_var, dim) in enumerate(zip(loop_vars, dims)):
            pad = "  " * (depth + 1)
            lines.append(f"{pad}var {loop_var}: Int64 = 0")
            lines.append(f"{pad}while ({loop_var} < {dim}) {{")

        pad = "  " * (loop_count + 1)
        lines.append(f"{pad}transparentCrc({arg}, \"{display_name}\", printHashValue)")

        for depth in range(loop_count - 1, -1, -1):
            loop_var = loop_vars[depth]
            pad = "  " * (depth + 1)
            lines.append(f"{pad}  {loop_var} += 1")
            lines.append(f"{pad}}}")

        return lines

    def _emit_checksum_main(self, entry: Function, decls: list[TopDecl]) -> str:
        checksum_vars = self._load_checksum_vars()
        globals_by_name = {
            decl.name: decl
            for decl in decls
            if isinstance(decl, GlobalVar)
        }

        lines = [
            "main() {",
            "  let printHashValue: Int64 = 0",
            "  platformMainBegin()",
            "  crc32Gentab()",
            f"  {entry.name}()",
        ]
        for idx, (var_name, display_name) in enumerate(checksum_vars):
            lines.extend(self._emit_checksum_item(var_name, display_name, globals_by_name, idx))
        lines.append("  platformMainEnd(finalChecksum(), printHashValue)")
        lines.append("}")
        return "\n".join(lines)

    def emit_global_var(self, gv: GlobalVar) -> str:
        old = self._emitting_global
        self._emitting_global = True
        try:
            return super().emit_global_var(gv)
        finally:
            self._emitting_global = old

    def emit_module(self, module) -> str:
        self._global_ptr_aliases = {}
        self._ptr_aliases = self._global_ptr_aliases
        self._global_ptr_arrays = {}
        self._ptr_arrays = self._global_ptr_arrays
        text = super().emit_module(module)
        decls = getattr(module, "decls", None) or []
        has_main = any(isinstance(decl, Function) and decl.name == "main" for decl in decls)
        if has_main:
            return cangjie_c_helpers() + "\n\n" + text

        entry = next(
            (
                decl for decl in decls
                if isinstance(decl, Function) and not decl.params
            ),
            None,
        )
        if entry is None:
            return cangjie_c_helpers() + "\n\n" + text

        return csmith_checksum_runtime() + "\n\n" + text + "\n" + self._emit_checksum_main(entry, decls) + "\n"

    def emit_function(self, fn: Function) -> str:
        saved_aliases = self._ptr_aliases
        saved_arrays = self._ptr_arrays
        self._ptr_aliases = dict(self._global_ptr_aliases)
        self._ptr_arrays = dict(self._global_ptr_arrays)
        params = ", ".join(f"{p.name}: {self.emit_type(p.ty)}" for p in fn.params)

        try:
            if fn.name == "main":
                header = f"main({params}) {{" if params else "main() {"
                lines = [header]
                lines += self.emit_block(fn.body, indent=1)
                lines.append("}")
                return "\n".join(lines)

            header = f"{self.fn_kw} {fn.name}({params}){self.fn_ret_sep} {self.emit_type(fn.ret_ty)} {{"
            lines = [header]
            lines += self.emit_block(fn.body, indent=1)
            lines.append("}")
            return "\n".join(lines)
        finally:
            self._ptr_aliases = saved_aliases
            self._ptr_arrays = saved_arrays

    def emit_type(self, ty: Type) -> str:
        if (ty.kind == "int") and ty.bits == 32:
            return "Int32" if ty.signed.name == "SIGNED" else "UInt32"
        if (ty.kind == "int") and ty.bits == 64:
            return "Int64" if ty.signed.name == "SIGNED" else "UInt64"
        if ty.kind == "bool":
            return "Bool"
        
        if ty.kind == "ptr":
            elem = ty.elem
            if elem is None:
                return "CPointer<Unit>"
            return f"CPointer<{self.emit_type(elem)}>"

        if ty.kind == "array":
            elem = ty.elem
            n = ty.length
            if elem is None:
                return "Array<Int32>"
            if n is not None:
                return f"VArray<{self.emit_type(elem)}, ${int(n)}>"
            return f"Array<{self.emit_type(elem)}>"
        
        if ty.kind == "struct":
            return f"{ty.name}"

        raise NotImplementedError(ty)

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from translator.backend.emitters import cangjie_c_helpers, csmith_checksum_runtime
from translator.backend.ruleset import RuleMissing, RuleSet
from translator.ir.nodes import (
    BinOp,
    Block,
    BlockStmt,
    Expr,
    FieldDecl,
    Function,
    GlobalVar,
    Module,
    Stmt,
    StructDecl,
    TopDecl,
    UnOp,
    Var,
    VarDecl,
)
from translator.ir.types import Signedness
from translator.ir.types import Type


BIN_OP = {
    BinOp.ADD: "+",
    BinOp.SUB: "-",
    BinOp.MUL: "*",
    BinOp.DIV: "/",
    BinOp.MOD: "%",
    BinOp.LT: "<",
    BinOp.LE: "<=",
    BinOp.GT: ">",
    BinOp.GE: ">=",
    BinOp.EQ: "==",
    BinOp.NE: "!=",
    BinOp.LAND: "&&",
    BinOp.LOR: "||",
    BinOp.BIT_AND: "&",
    BinOp.BIT_OR: "|",
    BinOp.BIT_XOR: "^",
    BinOp.SHL: "<<",
    BinOp.SHR: ">>",
}

UN_OP = {
    UnOp.NOT: "!",
}


class GeneratedCangjieEmitter:
    """Minimal emitter shell for emitter B.

    This class intentionally contains only target syntax primitives and generic
    dispatch. Node-specific emission must come from the generated RuleSet.
    """

    stmt_term = ""
    fn_kw = "func"
    fn_ret_sep = ":"

    def __init__(self, rules: RuleSet):
        self.rules = rules
        self._tmp_counter = 0

    def fresh_tmp(self) -> str:
        name = f"__b_tmp_{self._tmp_counter}"
        self._tmp_counter += 1
        return name

    def emit_expr(self, expr: Expr) -> str:
        fn = self.rules.expr(expr)
        return fn(self, expr)

    def emit_stmt(self, stmt: Stmt, indent: int) -> list[str]:
        fn = self.rules.stmt(stmt)
        return fn(self, stmt, indent)

    def emit_block(self, block: Block, indent: int) -> list[str]:
        lines: list[str] = []
        for stmt in block.stmts:
            lines.extend(self.emit_stmt(stmt, indent))
        return lines

    def emit_condition(self, expr: Expr) -> str:
        text = self.emit_expr(expr)
        ty = getattr(expr, "ty", None)
        if getattr(ty, "kind", None) == "bool":
            return text
        return f"({text} != 0)"

    def emit_function(self, fn: Function) -> str:
        params = ", ".join(f"{p.name}: {self.emit_type(p.ty)}" for p in fn.params)
        if fn.name == "main":
            header = f"main({params}) {{" if params else "main() {"
        else:
            header = f"{self.fn_kw} {fn.name}({params}){self.fn_ret_sep} {self.emit_type(fn.ret_ty)} {{"
        lines = [header]
        lines.extend(self.emit_block(fn.body, 1))
        lines.append("}")
        return "\n".join(lines)

    def emit_global_var(self, gv: GlobalVar) -> str:
        stmt = VarDecl(var=Var(name=gv.name, ty=gv.ty), init=gv.init)
        return "\n".join(self.emit_stmt(stmt, 0))

    def emit_struct_decl(self, st: StructDecl) -> str:
        lines = [f"struct {st.name} {{"]
        for field in st.fields:
            lines.append(f"  var {field.name}: {self.emit_type(field.ty)}")
        lines.append("}")
        return "\n".join(lines)

    def emit_module(self, module: Module) -> str:
        parts: list[str] = []
        for decl in module.decls:
            parts.append(self.emit_top_decl(decl))
        text = "\n\n".join(part for part in parts if part.strip()) + "\n"

        has_main = any(isinstance(decl, Function) and decl.name == "main" for decl in module.decls)
        if has_main:
            return cangjie_c_helpers() + "\n\n" + text

        entry = next(
            (
                decl for decl in module.decls
                if isinstance(decl, Function) and not decl.params
            ),
            None,
        )
        if entry is None:
            return cangjie_c_helpers() + "\n\n" + text

        return csmith_checksum_runtime() + "\n\n" + text + "\n" + self._emit_checksum_main(entry, module.decls) + "\n"

    def emit_top_decl(self, decl: TopDecl) -> str:
        if isinstance(decl, StructDecl):
            return self.emit_struct_decl(decl)
        if isinstance(decl, GlobalVar):
            return self.emit_global_var(decl)
        if isinstance(decl, Function):
            return self.emit_function(decl)
        raise RuleMissing("top decl", decl)

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

        if not indices or not dims:
            arg = self._checksum_arg(ref, globals_by_name)
            return [f"  transparentCrc({arg}, \"{display_name}\", printHashValue)"]

        loop_count = min(len(indices), len(dims))
        loop_vars = [f"__ck_b_{item_index}_{i}" for i in range(loop_count)]
        expr = base + "".join(f"[{v}]" for v in loop_vars)
        arg = self._checksum_value_arg(expr, self._array_elem_ty(ty))

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

    def emit_type(self, ty: Type) -> str:
        if ty.kind == "void":
            return "Unit"
        if ty.kind == "bool":
            return "Bool"
        if ty.kind == "int":
            if ty.bits == 64:
                return "Int64" if ty.signed.name == "SIGNED" else "UInt64"
            return "Int32" if ty.signed.name == "SIGNED" else "UInt32"
        if ty.kind == "float":
            return "Float64"
        if ty.kind == "array":
            elem = self.emit_type(ty.elem) if ty.elem is not None else "Int32"
            if ty.length is not None:
                return f"VArray<{elem}, ${int(ty.length)}>"
            return f"Array<{elem}>"
        if ty.kind == "ptr":
            elem = self.emit_type(ty.elem) if ty.elem is not None else "Unit"
            return f"CPointer<{elem}>"
        if ty.kind == "struct":
            return str(ty.name)
        raise NotImplementedError(f"unsupported type in emitter B: {ty}")

    def emit_op(self, op: BinOp) -> str:
        try:
            return BIN_OP[op]
        except KeyError as e:
            raise NotImplementedError(f"unsupported binary op in emitter B: {op}") from e

    def emit_unary_op(self, op: UnOp) -> str:
        try:
            return UN_OP[op]
        except KeyError as e:
            raise NotImplementedError(f"unsupported unary op in emitter B: {op}") from e

from __future__ import annotations

from translator.backend.ruleset import RuleSet

from translator.ir.nodes import (
    Literal, Var, Binary, Unary, Cast,
    VarDecl, Assign, Return, If, While,
)

from translator.backend.carbon_emitter import (
    emit_literal, emit_var, emit_binary, emit_unary, emit_cast,
    emit_vardecl, emit_assign, emit_return, emit_if, emit_while,
)

DEFAULT_CARBON_RULES = RuleSet(
    expr_emitters={
        Literal: emit_literal,
        Var: emit_var,
        Binary: emit_binary,
        Unary: emit_unary,
        Cast: emit_cast,
    },
    stmt_emitters={
        VarDecl: emit_vardecl,
        Assign: emit_assign,
        Return: emit_return,
        If: emit_if,
        While: emit_while,
    },
)

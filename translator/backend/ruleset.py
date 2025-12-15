from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Type

from translator.ir.nodes import Expr, Stmt

ExprEmitter = Callable[[object, Expr], str]
StmtEmitter = Callable[[object, Stmt, int], list[str]]

@dataclass(frozen=True)
class RuleSet:
    expr_emitters: Dict[Type[Expr], ExprEmitter]
    stmt_emitters: Dict[Type[Stmt], StmtEmitter]

    def expr(self, node: Expr) -> ExprEmitter:
        try:
            return self.expr_emitters[type(node)]
        except KeyError:
            raise NotImplementedError(f"No expr rule for {type(node).__name__}")

    def stmt(self, node: Stmt) -> StmtEmitter:
        try:
            return self.stmt_emitters[type(node)]
        except KeyError:
            raise NotImplementedError(f"No stmt rule for {type(node).__name__}")

    def overlay(self, other: "RuleSet") -> "RuleSet":
        """
        规则叠加：other 覆盖 self（同类型节点时以 other 为准）
        """
        expr = dict(self.expr_emitters)
        expr.update(other.expr_emitters)
        stmt = dict(self.stmt_emitters)
        stmt.update(other.stmt_emitters)
        return RuleSet(expr_emitters=expr, stmt_emitters=stmt)

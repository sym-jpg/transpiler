from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union, List

from translator.ir.types import Type

LiteralValue = Union[int, float, bool]

class BinOp(str, Enum):
    ADD="ADD" #+
    SUB="SUB" #-
    MUL="MUL" #*
    DIV="DIV" #/
    LT="LT" #<
    LE="LE" #<=
    GT="GT" #>
    GE="GE" #>=
    EQ="EQ" #==
    NE="NE" #!=
    LAND="LAND" #&&
    LOR="LOR" #||

class UnOp(str, Enum):
    NOT="NOT"   # !

@dataclass(frozen=True)
class Expr:
    ty: Type


@dataclass(frozen=True)
class Literal(Expr):
    value: LiteralValue


@dataclass(frozen=True)
class Var(Expr):
    name: str


@dataclass(frozen=True)
class Cast(Expr):
    to_ty: Type
    expr: Expr

    def __post_init__(self):
        # Cast 的 Expr.ty 就是 to_ty
        object.__setattr__(self, "ty", self.to_ty)


@dataclass(frozen=True)
class Binary(Expr):
    op: BinOp
    lhs: Expr
    rhs: Expr

@dataclass(frozen=True)
class Unary(Expr):
    op: UnOp
    operand: Expr

# ---------- Statements ----------

@dataclass(frozen=True)
class Stmt:
    pass

@dataclass(frozen=True)
class ExprStmt(Stmt):
    expr: Expr

@dataclass(frozen=True)
class VarDecl(Stmt):
    var: Var
    init: Optional[Expr] = None

@dataclass(frozen=True)
class Assign(Stmt):
    target: Var
    value: Expr

@dataclass(frozen=True)
class Return(Stmt):
    value: Expr

@dataclass(frozen=True)
class Block(Stmt):
    stmts: List[Stmt]

@dataclass(frozen=True)
class BlockStmt(Stmt):
    block: Block

@dataclass(frozen=True)
class If(Stmt):
    cond: Expr
    then_body: Block
    else_body: Block | None = None

@dataclass(frozen=True)
class While(Stmt):
    cond: Expr
    body: Block

@dataclass(frozen=True)
class Function:
    name: str
    params: list[Var]
    ret_ty: Type
    body: Block

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union, List,  Any

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
    BIT_AND="BIT_AND" #&
    BIT_OR="BIT_OR" #|
    BIT_XOR="BIT_XOR" #^
    SHL="SHL" #<<
    SHR="SHR" #>>
    MOD="MOD" #%

class UnOp(str, Enum):
    NOT="NOT"   

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
        object.__setattr__(self, "ty", self.to_ty)

@dataclass(frozen=True)
class Call(Expr):
    callee: Any
    args: List[Any]

@dataclass(frozen=True)
class Binary(Expr):
    op: BinOp
    lhs: Expr
    rhs: Expr

@dataclass(frozen=True)
class Unary(Expr):
    op: UnOp
    operand: Expr


@dataclass(frozen=True)
class Conditional(Expr):
    cond: Expr
    then: Expr
    else_: Expr

@dataclass(frozen=True)
class AddrOf(Expr):
    expr: Expr

@dataclass(frozen=True)
class Deref(Expr):
    expr: Expr

@dataclass(frozen=True)
class Index(Expr):
    base: Expr
    index: Expr

@dataclass(frozen=True)
class Field(Expr):
    base: Expr
    name: Expr

@dataclass(frozen=True)
class Arrow(Expr):
    base: Expr
    name: Expr

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

LValue = Union[Var, Deref, Index, Field, Arrow]

@dataclass(frozen=True)
class Assign(Stmt):
    target: LValue
    value: Expr

@dataclass(frozen=True)
class Return(Stmt):
    value: Expr
    
@dataclass(frozen=True)
class Break(Stmt):
    pass

@dataclass(frozen=True)
class Continue(Stmt):
    pass

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
class InitList(Expr):
    elems: list[Expr]

@dataclass(frozen=True)
class Function:
    name: str
    params: list[Var]
    ret_ty: Type
    body: Block

@dataclass(frozen=True)
class GlobalVar:
    name: str
    ty: Type
    init: Optional[Expr] = None  # 先支持常量/字面量即可

@dataclass(frozen=True)
class FieldDecl:
    name: str
    ty: Type

@dataclass(frozen=True)
class StructDecl:
    name: str
    fields: List[FieldDecl]

TopDecl = Union[GlobalVar, StructDecl, Function]

@dataclass(frozen=True)
class Module:
    decls: List[TopDecl]

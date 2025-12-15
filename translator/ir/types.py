from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class Signedness(str, Enum):
    SIGNED = "signed"
    UNSIGNED = "unsigned"

@dataclass(frozen=True)
class Type:
    kind: str  # "int" | "bool" | "void"
    bits: int | None = None
    signed: Signedness | None = None

    @staticmethod
    def i32() -> Type:
        return Type(kind="int", bits=32, signed=Signedness.SIGNED)

    @staticmethod
    def u32() -> Type:
        return Type(kind="int", bits=32, signed=Signedness.UNSIGNED)
    
    @staticmethod
    def f32() -> "Type":
        return Type(kind="float", bits=32)

    @staticmethod
    def f64() -> "Type":
        return Type(kind="float", bits=64)

    @staticmethod
    def bool() -> Type:
        return Type(kind="bool")

    @staticmethod
    def void() -> Type:
        return Type(kind="void")

    def short(self) -> str:
        if self.kind == "int":
            s = "I" if self.signed == Signedness.SIGNED else "U"
            return f"{s}{self.bits}"
        if self.kind == "bool":
            return "Bool"
        if self.kind == "void":
            return "Void"
        if self.kind == "float":
            return f"F{self.bits}"
        return self.kind

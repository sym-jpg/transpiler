from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class Signedness(str, Enum):
    SIGNED = "signed"
    UNSIGNED = "unsigned"

@dataclass(frozen=True)
class Type:
    kind: str  # "int" | "bool" | "void"
    bits: int | None = None
    signed: Signedness | None = None

    elem: Optional["Type"] = None   
    length: Optional[int] = None    
    name: str | None  = None

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
    def i64():
        return Type(kind="int", bits=64, signed=Signedness.SIGNED)
    
    @staticmethod
    def void() -> Type:
        return Type(kind="void")
    
    @staticmethod
    def ptr(elem: Type) -> Type:
        return Type(kind="ptr", elem=elem)

    @staticmethod
    def array(elem: Type, length: Optional[int]) -> Type:
        return Type(kind="array", elem=elem, length=length)
    
    @staticmethod
    def struct(name: str) -> Type:
        return Type(kind="struct", name=name)

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
        if self.kind == "ptr":
            return f"*{self.elem.short() if self.elem else '<?> '}"
        if self.kind == "array":
            n = self.length if self.length is not None else "?"
            return f"[{n}]{self.elem.short() if self.elem else '<?> '}"
        return self.kind

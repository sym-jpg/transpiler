from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ErrorCode(str, Enum):
    E_INTERNAL = "E_INTERNAL"
    E_INVALID_IR = "E_INVALID_IR"


@dataclass(frozen=True)
class Diagnostic(Exception):
    code: ErrorCode
    message: str
    node_hint: Optional[str] = None

    def __str__(self) -> str:
        if self.node_hint:
            return f"{self.code}: {self.message} @ {self.node_hint}"
        return f"{self.code}: {self.message}"

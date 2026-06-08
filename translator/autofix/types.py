from dataclasses import dataclass
from enum import Enum
from typing import Optional

class IssueKind(str, Enum):
    MISSING_EXPR_RULE = "MISSING_EXPR_RULE"
    MISSING_STMT_RULE = "MISSING_STMT_RULE"
    LOWERING_NOT_IMPLEMENTED = "LOWERING_NOT_IMPLEMENTED"
    COMPILER_ERROR = "COMPILER_ERROR"
    OTHER = "OTHER"

@dataclass
class Issue:
    kind: IssueKind
    message: str
    node_type: Optional[str] = None  # e.g. "CallExpr" / "CursorKind.CALL_EXPR"
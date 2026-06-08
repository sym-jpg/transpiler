from __future__ import annotations
import re
from .types import Issue, IssueKind

_RE_NO_EXPR = re.compile(r"No expr rule for (\w+)")
_RE_NO_STMT = re.compile(r"No stmt rule for (\w+)")
_RE_NOTIMPL_KIND = re.compile(r"NotImplementedError:\s*(CursorKind\.\w+)")
_RE_NOTIMPL_GENERIC = re.compile(r"NotImplementedError:\s*(.+)")
_RE_CJ_ERR = re.compile(r"error:\s|Runtime Exception:|warning:", re.IGNORECASE)
_RE_CARBON_ERR = re.compile(r"SYNTAX ERROR:|COMPILATION ERROR:", re.IGNORECASE)

def classify(log: str) -> Issue:
    m = _RE_NO_EXPR.search(log)
    if m:
        return Issue(IssueKind.MISSING_EXPR_RULE, log, node_type=m.group(1))

    m = _RE_NO_STMT.search(log)
    if m:
        return Issue(IssueKind.MISSING_STMT_RULE, log, node_type=m.group(1))

    m = _RE_NOTIMPL_KIND.search(log)
    if m:
        return Issue(IssueKind.LOWERING_NOT_IMPLEMENTED, log, node_type=m.group(1))

    m = _RE_NOTIMPL_GENERIC.search(log)
    if m:
        return Issue(IssueKind.LOWERING_NOT_IMPLEMENTED, log, node_type=m.group(1))

    if _RE_CARBON_ERR.search(log) or _RE_CJ_ERR.search(log):
        return Issue(IssueKind.COMPILER_ERROR, log)

    return Issue(IssueKind.OTHER, log)
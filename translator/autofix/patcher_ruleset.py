from __future__ import annotations

from .types import Issue, IssueKind
from .autogen_rules_from_llm import autogen_one
import importlib
from pathlib import Path
def _autogen_path() -> Path:
    return Path(__file__).resolve().parents[1] / "backend" / "ruleset_autogen.py"


def _sanity_check_autogen(issue: Issue) -> bool:
    """Verify that ruleset_autogen.py can be imported and contains the expected mapping."""
    if not issue.node_type:
        return False

    try:
        import translator.backend.ruleset_autogen as m
        importlib.reload(m)

        import translator.ir.nodes as nodes
        node_cls = getattr(nodes, issue.node_type, None)
        if node_cls is None:
            return False

        rules = getattr(m, "AUTOGEN_RULES", None)
        if rules is None:
            return False

        if issue.kind == IssueKind.MISSING_EXPR_RULE:
            mapping = getattr(rules, "expr_emitters", None)
        elif issue.kind == IssueKind.MISSING_STMT_RULE:
            mapping = getattr(rules, "stmt_emitters", None)
        else:
            return False

        if not isinstance(mapping, dict):
            return False

        fn = mapping.get(node_cls)
        return callable(fn)

    except Exception:
        return False



def patch_autogen_ruleset(issue: Issue) -> bool:
    if issue.kind == IssueKind.MISSING_EXPR_RULE:
        if not issue.node_type:
            return False
        changed = autogen_one("expr", issue.node_type)
        if not changed:
            return False
        if _sanity_check_autogen(issue):
            return True
        p = _autogen_path()
        if p.exists():
            p.unlink()
        return False

    if issue.kind == IssueKind.MISSING_STMT_RULE:
        if not issue.node_type:
            return False
        changed = autogen_one("stmt", issue.node_type)
        if not changed:
            return False
        if _sanity_check_autogen(issue):
            return True
        p = _autogen_path()
        if p.exists():
            p.unlink()
        return False

    return False
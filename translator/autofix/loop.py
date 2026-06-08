from __future__ import annotations
from .runner import run_frontend
from .classifier import classify
from .patcher_ruleset import patch_autogen_ruleset

def autofix(abs_path: str, max_iters: int = 6) -> bool:
    for i in range(max_iters):
        r = run_frontend(abs_path)
        if r.ok:
            print("[autofix] OK")
            return True

        log = (r.stdout or "") + "\n" + (r.stderr or "")
        issue = classify(log)
        print(f"[autofix] iter={i} kind={issue.kind} node={issue.node_type}")

        changed = patch_autogen_ruleset(issue)
        if changed:
            print("[autofix] wrote ruleset_autogen.py, retry...")
            continue

        print("[autofix] no patch for this issue yet, stop.")
        print(log)
        return False

    print("[autofix] reached max_iters")
    return False
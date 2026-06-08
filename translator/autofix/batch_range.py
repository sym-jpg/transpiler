from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from .runner import run_frontend
from .sanitize import sanitize_c
from .classifier import classify
from .patcher_ruleset import patch_autogen_ruleset
from .types import IssueKind
from .stats_lowering import LoweringStats


def sh(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def generate_raw(seed: int, flags_sh: Path, prob_txt: Path, out_c: Path) -> None:
    out_c.parent.mkdir(parents=True, exist_ok=True)
    cmd = f'{flags_sh} --seed {seed} --prob {prob_txt} > "{out_c}"'
    sh(["bash", "-lc", cmd])


def run_one(src_c: Path, max_rule_iters: int = 3) -> tuple[bool, str]:
    
    for _ in range(max_rule_iters):
        r = run_frontend(str(src_c))
        if r.ok:
            return True, ""
        log = (r.stdout or "") + "\n" + (r.stderr or "")
        issue = classify(log)

        if issue.kind in (IssueKind.MISSING_EXPR_RULE, IssueKind.MISSING_STMT_RULE):
            if patch_autogen_ruleset(issue):
                continue

        if issue.kind == IssueKind.LOWERING_NOT_IMPLEMENTED:
            return False, issue.node_type or ""

        return False, ""
    return False, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-from", type=int, required=True)
    ap.add_argument("--seed-to", type=int, required=True)
    ap.add_argument("--flags-sh", type=str, required=True)   # e.g. csmith/profile_v0/flags_v0.sh
    ap.add_argument("--prob-txt", type=str, required=True)   # e.g. csmith/profile_v0/prob_v0.txt
    ap.add_argument("--raw-dir", type=str, default="dataset/cases/raw")
    ap.add_argument("--san-dir", type=str, default="dataset/cases/raw_sanitized")
    ap.add_argument("--report-json", type=str, default="reports/lowering_missing.json")
    ap.add_argument("--report-md", type=str, default="reports/lowering_missing.md")
    args = ap.parse_args()

    seed_from = args.seed_from
    seed_to = args.seed_to

    flags_sh = Path(args.flags_sh)
    prob_txt = Path(args.prob_txt)
    raw_dir = Path(args.raw_dir)
    san_dir = Path(args.san_dir)

    stats = LoweringStats(max_examples_per_kind=10)

    for s in range(seed_from, seed_to + 1):
        raw_c = raw_dir / f"case_{s}.c"
        san_c = san_dir / f"case_{s}.c"

        generate_raw(s, flags_sh, prob_txt, raw_c)
        text = raw_c.read_text(encoding="utf-8", errors="replace")
        new_text = sanitize_c(text)
        san_c.write_text(new_text, encoding="utf-8")

        ok, kind = run_one(san_c)
        if (not ok) and kind:
            stats.record(kind, str(san_c))

        print(f"[batch] seed={s} ok={ok} missing={kind} src={san_c.name}")

    stats.write_json(args.report_json)
    stats.write_md(args.report_md, seed_from=seed_from, seed_to=seed_to)
    print(f"[batch] wrote {args.report_json} and {args.report_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
from __future__ import annotations

import argparse
import difflib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from translator.manual_pairs.pair_context import ManualPair, load_pairs


@dataclass
class PairResult:
    case: str
    level: str
    csmith_profile: str
    features: list[str]
    translate_ok: bool
    reference_exists: bool
    generated_path: str
    same_as_reference: bool | None
    error: str = ""


def _normalize_text(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def _run_translate(
    pair: ManualPair,
    out_cj: Path,
    *,
    timeout: int,
    autofix_iters: int,
    frontend: str,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    meta = pair.case_dir / "checksum_vars.json"
    if meta.is_file():
        env["CHECKSUM_VARS_JSON"] = str(meta.resolve())

    module = "translator.frontend.clang_frontend_b" if frontend == "b" else "translator.frontend.clang_frontend"
    cmd = [
        sys.executable,
        "-m",
        module,
        str(pair.core_c),
    ]
    if frontend == "a":
        cmd.extend(["--autofix-iters", str(autofix_iters)])
    cmd.extend(["--out", str(out_cj)])
    return subprocess.run(
        cmd,
        cwd=str(Path.cwd()),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def _write_diff(reference: Path, generated: Path, diff_path: Path) -> None:
    ref_lines = _normalize_text(reference.read_text(encoding="utf-8", errors="replace")).splitlines(True)
    gen_lines = _normalize_text(generated.read_text(encoding="utf-8", errors="replace")).splitlines(True)
    diff = difflib.unified_diff(
        ref_lines,
        gen_lines,
        fromfile=str(reference),
        tofile=str(generated),
    )
    diff_path.write_text("".join(diff), encoding="utf-8")


def eval_pair(
    pair: ManualPair,
    out_root: Path,
    *,
    root: Path,
    timeout: int,
    autofix_iters: int,
    compare_reference: bool,
    frontend: str,
) -> PairResult:
    rel = pair.case_dir.relative_to(root)
    out_dir = out_root / rel
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = out_dir / "generated.cj"

    try:
        proc = _run_translate(pair, generated, timeout=timeout, autofix_iters=autofix_iters, frontend=frontend)
    except subprocess.TimeoutExpired as e:
        return PairResult(
            case=str(rel),
            level=pair.level,
            csmith_profile=pair.csmith_profile,
            features=list(pair.features),
            translate_ok=False,
            reference_exists=pair.reference_cj.is_file(),
            generated_path=str(generated),
            same_as_reference=None,
            error=f"translate timeout after {timeout}s: {e}",
        )

    (out_dir / "translate.stdout").write_text(proc.stdout, encoding="utf-8")
    (out_dir / "translate.stderr").write_text(proc.stderr, encoding="utf-8")

    if proc.returncode != 0:
        return PairResult(
            case=str(rel),
            level=pair.level,
            csmith_profile=pair.csmith_profile,
            features=list(pair.features),
            translate_ok=False,
            reference_exists=pair.reference_cj.is_file(),
            generated_path=str(generated),
            same_as_reference=None,
            error=f"translate failed with returncode {proc.returncode}",
        )

    same: bool | None = None
    if compare_reference:
        ref_text = _normalize_text(pair.reference_cj.read_text(encoding="utf-8", errors="replace"))
        gen_text = _normalize_text(generated.read_text(encoding="utf-8", errors="replace"))
        same = ref_text == gen_text
        if not same:
            _write_diff(pair.reference_cj, generated, out_dir / "reference.diff")

    return PairResult(
        case=str(rel),
        level=pair.level,
        csmith_profile=pair.csmith_profile,
        features=list(pair.features),
        translate_ok=True,
        reference_exists=pair.reference_cj.is_file(),
        generated_path=str(generated),
        same_as_reference=same,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m translator.manual_pairs.eval",
        description="Evaluate manually curated C/Cangjie pairs against the current Cangjie emitter.",
    )
    parser.add_argument("--root", default="dataset/manual_pairs")
    parser.add_argument("--out-dir", default="dataset/manual_pair_eval")
    parser.add_argument("--feature", action="append", default=[], help="Only run pairs containing this feature. Repeatable.")
    parser.add_argument("--compare-reference", action="store_true", help="Also compare generated.cj with reference.cj text.")
    parser.add_argument("--autofix-iters", type=int, default=0)
    parser.add_argument("--frontend", choices=["a", "b"], default="a")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    pairs = load_pairs(root)
    if args.feature:
        wanted = set(args.feature)
        pairs = [pair for pair in pairs if not wanted.isdisjoint(pair.features)]

    results = [
        eval_pair(
            pair,
            out_root,
            root=root,
            timeout=args.timeout,
            autofix_iters=args.autofix_iters,
            compare_reference=args.compare_reference,
            frontend=args.frontend,
        )
        for pair in pairs
    ]

    payload = {
        "root": str(root),
        "total": len(results),
        "translate_pass": sum(1 for r in results if r.translate_ok),
        "translate_fail": sum(1 for r in results if not r.translate_ok),
        "same_as_reference": sum(1 for r in results if r.same_as_reference is True),
        "different_from_reference": sum(1 for r in results if r.same_as_reference is False),
        "results": [r.__dict__ for r in results],
    }
    (out_root / "summary.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(
        "[manual-pairs] "
        f"total={payload['total']} translate_pass={payload['translate_pass']} "
        f"translate_fail={payload['translate_fail']} same_as_reference={payload['same_as_reference']} "
        f"different_from_reference={payload['different_from_reference']}"
    )
    print(f"[manual-pairs] wrote {out_root / 'summary.json'}")

    return 0 if payload["translate_fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

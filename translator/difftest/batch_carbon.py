from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from sanitizer.sanitize_csmith import sanitize_csmith


@dataclass
class CmdResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int
    duration_seconds: float


def run_cmd(cmd: list[str], *, cwd: Path, timeout: int) -> CmdResult:
    start = time.perf_counter()
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return CmdResult(p.returncode == 0, p.stdout, p.stderr, p.returncode, time.perf_counter() - start)
    except subprocess.TimeoutExpired as e:
        return CmdResult(False, e.stdout or "", e.stderr or f"timeout after {timeout}s", 124, time.perf_counter() - start)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def generate_raw(seed: int, flags_sh: Path, prob_txt: Path, out_c: Path, cwd: Path, timeout: int) -> CmdResult:
    result = run_cmd(
        ["bash", str(flags_sh), "--seed", str(seed), "--prob", str(prob_txt)],
        cwd=cwd,
        timeout=timeout,
    )
    if result.ok:
        write_text(out_c, result.stdout)
    return result


def translate_to_carbon(core_c: Path, out_carbon: Path, cwd: Path, timeout: int) -> CmdResult:
    return run_cmd(
        [
            sys.executable,
            "-m",
            "translator.frontend.clang_frontend_carbon",
            str(core_c),
            "--out",
            str(out_carbon),
        ],
        cwd=cwd,
        timeout=timeout,
    )


def record_failure(case_dir: Path, stage: str, result: CmdResult | None, extra: dict[str, object]) -> None:
    payload = {"stage": stage, **extra}
    if result is not None:
        payload.update(
            {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration_seconds": round(result.duration_seconds, 6),
            }
        )
    write_text(case_dir / "failure.json", json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m translator.difftest.batch_carbon",
        description="Run large-scale Csmith generation and C-to-Carbon translation tests.",
    )
    parser.add_argument("--seed-from", type=int, required=True)
    parser.add_argument("--seed-to", type=int, required=True)
    parser.add_argument("--flags-sh", default="Csmith/profile_carbon_basic/flags_carbon_basic.sh")
    parser.add_argument("--prob-txt", default="Csmith/profile_carbon_basic/prob_carbon_basic.txt")
    parser.add_argument("--out-dir", default="dataset/difftest_carbon")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--stop-on-fail", action="store_true")
    args = parser.parse_args(argv)

    cwd = Path.cwd()
    out_dir = Path(args.out_dir)
    if args.clean and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results_jsonl = out_dir / "results.jsonl"
    if results_jsonl.exists():
        results_jsonl.unlink()

    summary = {
        "total": 0,
        "pass": 0,
        "generate_fail": 0,
        "translate_fail": 0,
    }
    run_start = time.perf_counter()

    flags_sh = (cwd / args.flags_sh).resolve()
    prob_txt = (cwd / args.prob_txt).resolve()

    for seed in range(args.seed_from, args.seed_to + 1):
        case_start = time.perf_counter()
        summary["total"] += 1
        case_dir = out_dir / f"seed_{seed}"
        raw_c = case_dir / "raw.c"
        core_c = case_dir / "core.c"
        out_carbon = case_dir / "test.carbon"
        row: dict[str, object] = {"seed": seed, "case_dir": str(case_dir)}

        generated = generate_raw(seed, flags_sh, prob_txt, raw_c, cwd, args.timeout)
        row["generate_seconds"] = round(generated.duration_seconds, 6)
        if not generated.ok:
            summary["generate_fail"] += 1
            row["status"] = "generate_fail"
            row["case_seconds"] = round(time.perf_counter() - case_start, 6)
            record_failure(case_dir, "generate", generated, row)
            append_jsonl(results_jsonl, row)
            print(f"[carbon-diff] seed={seed} generate_fail")
            if args.stop_on_fail:
                break
            continue

        core_code, checksum_vars = sanitize_csmith(raw_c.read_text(encoding="utf-8", errors="replace"))
        write_text(core_c, core_code)
        write_text(case_dir / "checksum_vars.json", json.dumps({"checksum_vars": checksum_vars}, indent=2, ensure_ascii=False) + "\n")

        translated = translate_to_carbon(core_c, out_carbon, cwd, args.timeout)
        row["translate_seconds"] = round(translated.duration_seconds, 6)
        if not translated.ok:
            summary["translate_fail"] += 1
            row["status"] = "translate_fail"
            row["case_seconds"] = round(time.perf_counter() - case_start, 6)
            record_failure(case_dir, "translate", translated, row)
            append_jsonl(results_jsonl, row)
            print(f"[carbon-diff] seed={seed} translate_fail")
            if args.stop_on_fail:
                break
            continue

        summary["pass"] += 1
        row["status"] = "pass"
        row["case_seconds"] = round(time.perf_counter() - case_start, 6)
        append_jsonl(results_jsonl, row)
        print(f"[carbon-diff] seed={seed} pass")

    elapsed = time.perf_counter() - run_start
    summary["elapsed_seconds"] = round(elapsed, 6)
    summary["avg_seconds_per_case"] = round(elapsed / summary["total"], 6) if summary["total"] else 0
    write_text(out_dir / "summary.json", json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(f"[carbon-diff] summary {json.dumps(summary, ensure_ascii=False)}")
    print(f"[carbon-diff] wrote {results_jsonl} and {out_dir / 'summary.json'}")
    return 0 if summary["pass"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

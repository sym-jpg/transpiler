from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from sanitizer.sanitize_csmith import sanitize_csmith


CHECKSUM_RE = re.compile(r"checksum\s*=\s*([0-9A-Fa-f]+)")


@dataclass
class CmdResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int
    duration_seconds: float


def run_cmd(cmd: list[str], *, cwd: Path, timeout: int, env: dict[str, str] | None = None) -> CmdResult:
    start = time.perf_counter()
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return CmdResult(p.returncode == 0, p.stdout, p.stderr, p.returncode, time.perf_counter() - start)
    except subprocess.TimeoutExpired as e:
        return CmdResult(
            False,
            e.stdout or "",
            e.stderr or f"timeout after {timeout}s",
            124,
            time.perf_counter() - start,
        )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def extract_checksum(output: str) -> str | None:
    matches = CHECKSUM_RE.findall(output)
    if not matches:
        return None
    raw = matches[-1]
    value = int(raw, 16)
    return f"{value & 0xFFFFFFFF:08X}"


def generate_raw(seed: int, flags_sh: Path, prob_txt: Path, out_c: Path, cwd: Path, timeout: int) -> CmdResult:
    out_c.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "bash",
        str(flags_sh),
        "--seed",
        str(seed),
        "--prob",
        str(prob_txt),
    ]
    result = run_cmd(cmd, cwd=cwd, timeout=timeout)
    if result.ok:
        out_c.write_text(result.stdout, encoding="utf-8")
    return result


def translate_to_cj(
    core_c: Path,
    meta_json: Path,
    out_cj: Path,
    cwd: Path,
    timeout: int,
    *,
    frontend: str,
) -> CmdResult:
    env = os.environ.copy()
    env["CHECKSUM_VARS_JSON"] = str(meta_json.resolve())
    module = "translator.frontend.clang_frontend_b" if frontend == "b" else "translator.frontend.clang_frontend"
    cmd = [
        sys.executable,
        "-m",
        module,
        str(core_c),
    ]
    if frontend == "a":
        cmd.extend(["--autofix-iters", "0"])
    cmd.extend(["--out", str(out_cj)])
    return run_cmd(
        cmd,
        cwd=cwd,
        timeout=timeout,
        env=env,
    )


def compile_and_run_c(
    raw_c: Path,
    exe: Path,
    *,
    cc: str,
    csmith_include: Path,
    cwd: Path,
    timeout: int,
) -> tuple[CmdResult, CmdResult | None, str | None]:
    exe.parent.mkdir(parents=True, exist_ok=True)
    compile_result = run_cmd(
        [cc, "-I", str(csmith_include), str(raw_c), "-o", str(exe)],
        cwd=cwd,
        timeout=timeout,
    )
    if not compile_result.ok:
        return compile_result, None, None

    run_result = run_cmd([str(exe)], cwd=cwd, timeout=timeout)
    return compile_result, run_result, extract_checksum(run_result.stdout + "\n" + run_result.stderr)


def compile_and_run_cj(
    cj: Path,
    exe: Path,
    *,
    cjc: str,
    cj_sysroot: Path | None,
    cj_set_runtime_rpath: bool,
    cwd: Path,
    timeout: int,
) -> tuple[CmdResult, CmdResult | None, str | None]:
    exe.parent.mkdir(parents=True, exist_ok=True)
    cmd = [cjc]
    if cj_sysroot is not None:
        cmd += ["--sysroot", str(cj_sysroot)]
    if cj_set_runtime_rpath:
        cmd.append("--set-runtime-rpath")
    cmd += [str(cj), "-o", str(exe)]
    compile_result = run_cmd(
        cmd,
        cwd=cwd,
        timeout=timeout,
    )
    if not compile_result.ok:
        return compile_result, None, None

    run_result = run_cmd([str(exe)], cwd=cwd, timeout=timeout)
    return compile_result, run_result, extract_checksum(run_result.stdout + "\n" + run_result.stderr)


def sdk_supports_arm64(sdk: Path) -> bool:
    tbd = sdk / "usr/lib/libSystem.tbd"
    if not tbd.is_file():
        return False
    try:
        head = tbd.read_text(encoding="utf-8", errors="ignore")[:2000]
    except OSError:
        return False
    return "arm64-macos" in head


def detect_macos_arm64_sdk() -> Path | None:
    candidates = [
        Path("/Library/Developer/CommandLineTools/SDKs/MacOSX15.5.sdk"),
        Path("/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk"),
        Path("/Library/Developer/CommandLineTools/SDKs/MacOSX15.2.sdk"),
        Path("/Library/Developer/CommandLineTools/SDKs/MacOSX14.5.sdk"),
    ]
    roots = [
        Path("/Library/Developer/CommandLineTools/SDKs"),
        Path("/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs"),
    ]
    for root in roots:
        if root.is_dir():
            candidates.extend(sorted(root.glob("MacOSX*.sdk"), reverse=True))

    seen: set[Path] = set()
    for sdk in candidates:
        resolved = sdk.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if sdk_supports_arm64(resolved):
            return resolved
    return None


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


def append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m translator.difftest.batch",
        description="Run Csmith C vs translated Cangjie checksum differential tests.",
    )
    ap.add_argument("--seed-from", type=int, required=True)
    ap.add_argument("--seed-to", type=int, required=True)
    ap.add_argument("--flags-sh", default="Csmith/profile_v0/flags_v0.sh")
    ap.add_argument("--prob-txt", default="Csmith/profile_v0/prob_v0.txt")
    ap.add_argument("--out-dir", default="dataset/difftest")
    ap.add_argument("--cc", default="gcc")
    ap.add_argument("--cjc", default="cjc")
    ap.add_argument(
        "--cj-sysroot",
        default="auto",
        help="Darwin SDK for cjc. Use 'auto' on macOS to pick a CLT SDK with arm64-macos; use 'none' to omit.",
    )
    ap.add_argument(
        "--no-cj-runtime-rpath",
        action="store_true",
        help="Do not pass --set-runtime-rpath to cjc.",
    )
    ap.add_argument(
        "--csmith-include",
        default=os.environ.get("CSMITH_INCLUDE", "/usr/local/include"),
        help="Directory containing csmith.h. Defaults to CSMITH_INCLUDE or /usr/local/include.",
    )
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--frontend", choices=["a", "b"], default="a", help="Translator frontend/backend route to use. Default: a.")
    ap.add_argument("--stop-on-fail", action="store_true")
    ap.add_argument("--clean", action="store_true")
    args = ap.parse_args(argv)

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
        "mismatch": 0,
        "generate_fail": 0,
        "translate_fail": 0,
        "c_compile_fail": 0,
        "c_run_fail": 0,
        "c_checksum_missing": 0,
        "cj_compile_fail": 0,
        "cj_run_fail": 0,
        "cj_checksum_missing": 0,
    }
    run_start = time.perf_counter()

    flags_sh = (cwd / args.flags_sh).resolve()
    prob_txt = (cwd / args.prob_txt).resolve()
    csmith_include = Path(args.csmith_include).expanduser()
    cj_sysroot: Path | None
    if args.cj_sysroot == "auto":
        cj_sysroot = detect_macos_arm64_sdk() if sys.platform == "darwin" else None
    elif args.cj_sysroot == "none":
        cj_sysroot = None
    else:
        cj_sysroot = Path(args.cj_sysroot).expanduser().resolve()
    if cj_sysroot is not None:
        print(f"[diff] using cjc sysroot: {cj_sysroot}")

    for seed in range(args.seed_from, args.seed_to + 1):
        case_start = time.perf_counter()
        summary["total"] += 1
        case_dir = out_dir / f"seed_{seed}"
        raw_c = case_dir / "raw.c"
        core_c = case_dir / "core.c"
        meta_json = case_dir / "checksum_vars.json"
        cj = case_dir / "test.cj"
        c_exe = case_dir / "a_c"
        cj_exe = case_dir / "a_cj"

        row: dict[str, object] = {"seed": seed, "case_dir": str(case_dir)}

        generated = generate_raw(seed, flags_sh, prob_txt, raw_c, cwd, args.timeout)
        row["generate_seconds"] = round(generated.duration_seconds, 6)
        if not generated.ok:
            summary["generate_fail"] += 1
            row.update({"status": "generate_fail", "case_seconds": round(time.perf_counter() - case_start, 6)})
            record_failure(case_dir, "generate", generated, row)
            append_jsonl(results_jsonl, row)
            print(f"[diff] seed={seed} generate_fail")
            if args.stop_on_fail:
                break
            continue

        core_code, checksum_vars = sanitize_csmith(raw_c.read_text(encoding="utf-8", errors="replace"))
        write_text(core_c, core_code)
        write_text(meta_json, json.dumps({"checksum_vars": checksum_vars}, indent=2, ensure_ascii=False) + "\n")

        translated = translate_to_cj(core_c, meta_json, cj, cwd, args.timeout, frontend=args.frontend)
        row["translate_seconds"] = round(translated.duration_seconds, 6)
        if not translated.ok:
            summary["translate_fail"] += 1
            row.update({"status": "translate_fail", "case_seconds": round(time.perf_counter() - case_start, 6)})
            record_failure(case_dir, "translate", translated, row)
            append_jsonl(results_jsonl, row)
            print(f"[diff] seed={seed} translate_fail")
            if args.stop_on_fail:
                break
            continue

        c_compile, c_run, c_checksum = compile_and_run_c(
            raw_c,
            c_exe,
            cc=args.cc,
            csmith_include=csmith_include,
            cwd=cwd,
            timeout=args.timeout,
        )
        row["c_compile_seconds"] = round(c_compile.duration_seconds, 6)
        if not c_compile.ok:
            summary["c_compile_fail"] += 1
            row.update({"status": "c_compile_fail", "case_seconds": round(time.perf_counter() - case_start, 6)})
            record_failure(case_dir, "c_compile", c_compile, row)
            append_jsonl(results_jsonl, row)
            print(f"[diff] seed={seed} c_compile_fail")
            if args.stop_on_fail:
                break
            continue
        if c_run is None or not c_run.ok:
            summary["c_run_fail"] += 1
            if c_run is not None:
                row["c_run_seconds"] = round(c_run.duration_seconds, 6)
            row.update({"status": "c_run_fail", "case_seconds": round(time.perf_counter() - case_start, 6)})
            record_failure(case_dir, "c_run", c_run, row)
            append_jsonl(results_jsonl, row)
            print(f"[diff] seed={seed} c_run_fail")
            if args.stop_on_fail:
                break
            continue
        if c_checksum is None:
            summary["c_checksum_missing"] += 1
            row.update({"status": "c_checksum_missing", "c_stdout": c_run.stdout, "c_stderr": c_run.stderr, "c_run_seconds": round(c_run.duration_seconds, 6), "case_seconds": round(time.perf_counter() - case_start, 6)})
            record_failure(case_dir, "c_checksum_missing", c_run, row)
            append_jsonl(results_jsonl, row)
            print(f"[diff] seed={seed} c_checksum_missing")
            if args.stop_on_fail:
                break
            continue

        cj_compile, cj_run, cj_checksum = compile_and_run_cj(
            cj,
            cj_exe,
            cjc=args.cjc,
            cj_sysroot=cj_sysroot,
            cj_set_runtime_rpath=not args.no_cj_runtime_rpath,
            cwd=cwd,
            timeout=args.timeout,
        )
        row["c_run_seconds"] = round(c_run.duration_seconds, 6)
        row["cj_compile_seconds"] = round(cj_compile.duration_seconds, 6)
        if not cj_compile.ok:
            summary["cj_compile_fail"] += 1
            row.update({"status": "cj_compile_fail", "c_checksum": c_checksum, "case_seconds": round(time.perf_counter() - case_start, 6)})
            record_failure(case_dir, "cj_compile", cj_compile, row)
            append_jsonl(results_jsonl, row)
            print(f"[diff] seed={seed} cj_compile_fail c={c_checksum}")
            if args.stop_on_fail:
                break
            continue
        if cj_run is None or not cj_run.ok:
            summary["cj_run_fail"] += 1
            if cj_run is not None:
                row["cj_run_seconds"] = round(cj_run.duration_seconds, 6)
            row.update({"status": "cj_run_fail", "c_checksum": c_checksum, "case_seconds": round(time.perf_counter() - case_start, 6)})
            record_failure(case_dir, "cj_run", cj_run, row)
            append_jsonl(results_jsonl, row)
            print(f"[diff] seed={seed} cj_run_fail c={c_checksum}")
            if args.stop_on_fail:
                break
            continue
        if cj_checksum is None:
            summary["cj_checksum_missing"] += 1
            row.update(
                {
                    "status": "cj_checksum_missing",
                    "c_checksum": c_checksum,
                    "cj_stdout": cj_run.stdout,
                    "cj_stderr": cj_run.stderr,
                    "cj_run_seconds": round(cj_run.duration_seconds, 6),
                    "case_seconds": round(time.perf_counter() - case_start, 6),
                }
            )
            record_failure(case_dir, "cj_checksum_missing", cj_run, row)
            append_jsonl(results_jsonl, row)
            print(f"[diff] seed={seed} cj_checksum_missing c={c_checksum}")
            if args.stop_on_fail:
                break
            continue

        row["cj_run_seconds"] = round(cj_run.duration_seconds, 6)
        row.update({"c_checksum": c_checksum, "cj_checksum": cj_checksum})
        if c_checksum == cj_checksum:
            summary["pass"] += 1
            row["status"] = "pass"
            print(f"[diff] seed={seed} pass checksum={c_checksum}")
        else:
            summary["mismatch"] += 1
            row["status"] = "mismatch"
            record_failure(case_dir, "mismatch", None, row)
            print(f"[diff] seed={seed} mismatch c={c_checksum} cj={cj_checksum}")
            if args.stop_on_fail:
                append_jsonl(results_jsonl, row)
                break

        row["case_seconds"] = round(time.perf_counter() - case_start, 6)
        append_jsonl(results_jsonl, row)

    elapsed = time.perf_counter() - run_start
    summary["elapsed_seconds"] = round(elapsed, 6)
    summary["avg_seconds_per_case"] = round(elapsed / summary["total"], 6) if summary["total"] else 0
    write_text(out_dir / "summary.json", json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(f"[diff] summary {json.dumps(summary, ensure_ascii=False)}")
    print(f"[diff] wrote {results_jsonl} and {out_dir / 'summary.json'}")
    return 0 if summary["pass"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

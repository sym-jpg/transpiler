from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from sanitizer.sanitize_csmith import sanitize_csmith


def _run_csmith(seed: int, flags_sh: Path, prob_txt: Path, *, timeout: int) -> str:
    proc = subprocess.run(
        [
            "bash",
            str(flags_sh),
            "--seed",
            str(seed),
            "--prob",
            str(prob_txt),
        ],
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Csmith generation failed for seed={seed}, returncode={proc.returncode}\n{proc.stderr}"
        )
    return proc.stdout


def scaffold_seed(
    seed: int,
    *,
    level: str,
    csmith_profile: str,
    out_root: Path,
    flags_sh: Path,
    prob_txt: Path,
    features: list[str],
    timeout: int,
    force: bool,
) -> Path:
    case_dir = out_root / level / f"seed_{seed:04d}"
    case_dir.mkdir(parents=True, exist_ok=True)

    raw_c = case_dir / "raw.c"
    core_c = case_dir / "core.c"
    meta_json = case_dir / "checksum_vars.json"
    features_json = case_dir / "features.json"
    reference_cj = case_dir / "reference.cj"

    if raw_c.exists() and not force:
        raw_code = raw_c.read_text(encoding="utf-8", errors="replace")
    else:
        raw_code = _run_csmith(seed, flags_sh, prob_txt, timeout=timeout)
        raw_c.write_text(raw_code, encoding="utf-8")

    core_code, checksum_vars = sanitize_csmith(raw_code)
    if force or not core_c.exists():
        core_c.write_text(core_code, encoding="utf-8")
    if force or not meta_json.exists():
        meta_json.write_text(
            json.dumps({"checksum_vars": checksum_vars}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if force or not features_json.exists():
        features_json.write_text(
            json.dumps(
                {
                    "seed": seed,
                    "level": level,
                    "csmith_profile": csmith_profile,
                    "csmith_flags": str(flags_sh),
                    "csmith_prob": str(prob_txt),
                    "features": features,
                    "note": "由 scaffold 工具生成，reference.cj 需要人工翻译后补充。",
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    if not reference_cj.exists():
        reference_cj.write_text(
            "// TODO: 人工翻译 core.c，并在通过编译运行后移除此占位内容。\n",
            encoding="utf-8",
        )

    return case_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m translator.manual_pairs.scaffold",
        description="Generate Csmith-derived manual C/Cangjie pair directories.",
    )
    parser.add_argument("--seed", type=int, action="append", required=True, help="Seed to generate. Repeatable.")
    parser.add_argument("--level", required=True, help="Complexity level directory, e.g. level_1_array.")
    parser.add_argument("--csmith-profile", default="profile_v0", help="Profile label recorded in features.json.")
    parser.add_argument("--out-root", default="dataset/manual_pairs")
    parser.add_argument("--flags-sh", default="Csmith/profile_v0/flags_v0.sh")
    parser.add_argument("--prob-txt", default="Csmith/profile_v0/prob_v0.txt")
    parser.add_argument("--feature", action="append", default=[], help="Feature label to write into features.json. Repeatable.")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--force", action="store_true", help="Overwrite generated raw/core/meta/features files.")
    args = parser.parse_args(argv)

    out_root = Path(args.out_root)
    flags_sh = Path(args.flags_sh).resolve()
    prob_txt = Path(args.prob_txt).resolve()

    for seed in args.seed:
        case_dir = scaffold_seed(
            seed,
            level=args.level,
            csmith_profile=args.csmith_profile,
            out_root=out_root,
            flags_sh=flags_sh,
            prob_txt=prob_txt,
            features=list(args.feature),
            timeout=args.timeout,
            force=args.force,
        )
        print(f"[manual-pairs] scaffolded {case_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

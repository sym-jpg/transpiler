from __future__ import annotations

import argparse
import json
import traceback
from dataclasses import dataclass
from pathlib import Path

from translator.autofix.ruleset_autogen_writer import apply_patch
from translator.manual_pairs.learn import (
    RuleSpec,
    autogen_backend_env,
    _eval_after_apply,
    _generate_rule,
    _parse_rule_spec,
    _sanity_check_autogen,
    build_rule_prompt,
    resolve_backend,
)


@dataclass(frozen=True)
class Stage:
    name: str
    level: str
    features: list[str]
    rules: list[RuleSpec]
    enabled: bool


def _load_plan(path: Path) -> tuple[str, Path, list[Stage]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    target = str(data.get("target", "Cangjie"))
    root = Path(str(data.get("root", "dataset/manual_pairs"))).resolve()
    stages: list[Stage] = []
    for item in data.get("stages", []):
        stages.append(
            Stage(
                name=str(item["name"]),
                level=str(item.get("level", "")),
                features=[str(x) for x in item.get("features", [])],
                rules=[_parse_rule_spec(str(x)) for x in item.get("rules", [])],
                enabled=bool(item.get("enabled", True)),
            )
        )
    return target, root, stages


def _proposal_path(out_dir: Path, stage: Stage, spec: RuleSpec) -> Path:
    return out_dir / stage.name / f"{spec.kind}_{spec.node}.json"


def _load_cached(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m translator.manual_pairs.iterate",
        description="Run staged LLM emitter-rule generation from a learning plan.",
    )
    parser.add_argument("--plan", default="dataset/manual_pairs/learning_plan.json")
    parser.add_argument("--out-dir", default="dataset/manual_pair_learn")
    parser.add_argument("--stage", action="append", default=[], help="Only run named stage. Repeatable.")
    parser.add_argument("--max-pairs", type=int, default=3)
    parser.add_argument("--backend", choices=["a", "b"], default="b", help="Autogen ruleset/backend to use. Default: b.")
    parser.add_argument("--dump-prompts", action="store_true", help="Write prompt files for the selected stages and do not call the LLM.")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--eval-each", action="store_true")
    parser.add_argument("--use-cache", action="store_true", help="Reuse existing proposal JSON instead of calling LLM.")
    parser.add_argument("--dry-run", action="store_true", help="Print the resolved plan without generating rules.")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args(argv)

    target, pair_root, stages = _load_plan(Path(args.plan))
    backend = resolve_backend(args.backend)
    selected = set(args.stage)
    if selected:
        stages = [stage for stage in stages if stage.name in selected]
    stages = [stage for stage in stages if stage.enabled]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.dump_prompts and (args.apply or args.eval_each):
        raise RuntimeError("--dump-prompts cannot be combined with --apply or --eval-each")

    if args.dry_run:
        for stage in stages:
            rule_text = ", ".join(f"{rule.kind}:{rule.node}" for rule in stage.rules)
            feature_text = ", ".join(stage.features)
            print(f"[iterate] stage={stage.name} level={stage.level} features=[{feature_text}] rules=[{rule_text}]")
        return 0

    summary: dict[str, object] = {
        "target": target,
        "root": str(pair_root),
        "backend": backend.name,
        "autogen_path": str(backend.autogen_path),
        "autogen_module": backend.autogen_module,
        "apply": bool(args.apply),
        "replace": bool(args.replace),
        "stages": [],
    }

    failed = False
    for stage in stages:
        stage_dir = out_dir / stage.name
        stage_dir.mkdir(parents=True, exist_ok=True)
        stage_result: dict[str, object] = {
            "name": stage.name,
            "level": stage.level,
            "features": stage.features,
            "rules": [],
        }

        print(f"[iterate] stage={stage.name}")
        for spec in stage.rules:
            rule_result: dict[str, object] = {
                "kind": spec.kind,
                "node": spec.node,
                "ok": False,
            }
            try:
                proposal_path = _proposal_path(out_dir, stage, spec)
                if args.dump_prompts:
                    prompt = build_rule_prompt(
                        spec,
                        target_name=target,
                        pair_root=pair_root,
                        features=stage.features,
                        max_pairs=args.max_pairs,
                    )
                    prompt_path = proposal_path.with_suffix(".prompt.md")
                    prompt_path.write_text(prompt, encoding="utf-8")
                    rule_result["prompt"] = str(prompt_path)
                    rule_result["ok"] = True
                    print(f"[iterate] wrote prompt {prompt_path}")
                    stage_result["rules"].append(rule_result)
                    continue

                data = _load_cached(proposal_path) if args.use_cache else None
                if data is None:
                    data = _generate_rule(
                        spec,
                        target_name=target,
                        pair_root=pair_root,
                        features=stage.features,
                        max_pairs=args.max_pairs,
                    )
                    proposal_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                    print(f"[iterate] wrote proposal {proposal_path}")
                else:
                    print(f"[iterate] reused proposal {proposal_path}")

                rule_result["func_name"] = data["func_name"]
                rule_result["proposal"] = str(proposal_path)

                if args.apply:
                    with autogen_backend_env(backend):
                        changed = apply_patch(
                            spec.kind,
                            spec.node,
                            str(data["func_name"]),
                            str(data["func_code"]),
                            replace=bool(args.replace),
                        )
                        _sanity_check_autogen(spec)
                    rule_result["changed"] = changed
                    print(f"[iterate] applied {spec.kind}:{spec.node} changed={changed}")

                rule_result["ok"] = True
            except Exception as exc:
                failed = True
                rule_result["error"] = str(exc)
                rule_result["traceback"] = traceback.format_exc()
                print(f"[iterate] failed {spec.kind}:{spec.node}: {exc}")
                if not args.continue_on_error:
                    stage_result["rules"].append(rule_result)
                    summary["stages"].append(stage_result)
                    (out_dir / "iterate_summary.json").write_text(
                        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    return 1
            stage_result["rules"].append(rule_result)

        if args.eval_each and args.apply:
            eval_summary = _eval_after_apply(
                pair_root,
                stage_dir / "eval",
                stage.features,
                args.timeout,
                frontend=backend.frontend,
            )
            stage_result["eval"] = eval_summary
            print(
                "[iterate] eval "
                f"stage={stage.name} total={eval_summary['total']} "
                f"pass={eval_summary['translate_pass']} fail={eval_summary['translate_fail']}"
            )
            if eval_summary["translate_fail"]:
                failed = True
                if not args.continue_on_error:
                    summary["stages"].append(stage_result)
                    (out_dir / "iterate_summary.json").write_text(
                        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    return 1

        summary["stages"].append(stage_result)

    (out_dir / "iterate_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[iterate] wrote {out_dir / 'iterate_summary.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

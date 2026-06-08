from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Dict, List


@dataclass
class LoweringStats:
    max_examples_per_kind: int = 5
    data: Dict[str, Dict[str, object]] = field(default_factory=dict)

    def record(self, kind: str, example_path: str) -> None:
        if not kind:
            kind = "<unknown>"
        entry = self.data.setdefault(kind, {"count": 0, "examples": []})
        entry["count"] = int(entry["count"]) + 1
        examples: List[str] = entry["examples"]  # type: ignore
        if len(examples) < self.max_examples_per_kind and example_path not in examples:
            examples.append(example_path)

    def write_json(self, out_path: str | Path) -> None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # sort by count desc
        sorted_items = sorted(
            self.data.items(),
            key=lambda kv: int(kv[1]["count"]),  # type: ignore
            reverse=True,
        )
        payload = {k: v for k, v in sorted_items}
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def write_md(self, out_path: str | Path, seed_from: int, seed_to: int) -> None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sorted_items = sorted(
            self.data.items(),
            key=lambda kv: int(kv[1]["count"]),  # type: ignore
            reverse=True,
        )

        def suggest(kind: str) -> str:
            if any(x in kind for x in ["PAREN_EXPR", "UNEXPOSED_EXPR", "IMPLICIT_CAST_EXPR"]):
                return "WRAP/UNWRAP"
            if any(x in kind for x in ["CSTYLE_CAST_EXPR", "CXX_", "STATIC_CAST", "REINTERPRET_CAST"]):
                return "CAST (likely unwrap first)"
            if any(x in kind for x in ["CONDITIONAL_OPERATOR", "ARRAY_SUBSCRIPT_EXPR", "INIT_LIST_EXPR"]):
                return "IR_EXTEND"
            return "LLM_PATCH_OK / TBD"

        lines: List[str] = []
        lines.append(f"# Lowering Missing Kinds Report\n")
        lines.append(f"- Time: {now}\n")
        lines.append(f"- Seed Range: [{seed_from}, {seed_to}]\n")
        lines.append(f"- Unique kinds: {len(sorted_items)}\n\n")

        lines.append("| CursorKind | Count | Suggested Action | Examples |\n")
        lines.append("|---|---:|---|---|\n")
        for kind, info in sorted_items:
            cnt = int(info["count"])  # type: ignore
            exs = info["examples"]  # type: ignore
            ex_str = "<br>".join(exs) if exs else ""
            lines.append(f"| `{kind}` | {cnt} | {suggest(kind)} | {ex_str} |\n")

        out_path.write_text("".join(lines), encoding="utf-8")
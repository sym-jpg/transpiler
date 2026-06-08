from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ManualPair:
    case_dir: Path
    core_c: Path
    reference_cj: Path
    level: str
    csmith_profile: str
    features: tuple[str, ...]
    note: str = ""


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def load_pairs(root: Path) -> list[ManualPair]:
    pairs: list[ManualPair] = []
    if not root.exists():
        return pairs

    for core_c in sorted(root.rglob("core.c")):
        case_dir = core_c.parent
        reference_cj = case_dir / "reference.cj"
        if not reference_cj.is_file():
            continue

        meta = _read_json(case_dir / "features.json")
        raw_features = meta.get("features", [])
        features = tuple(str(x) for x in raw_features if str(x).strip())
        level = str(meta.get("level", case_dir.parent.name))
        csmith_profile = str(meta.get("csmith_profile", "unknown"))
        note = str(meta.get("note", ""))
        pairs.append(
            ManualPair(
                case_dir=case_dir,
                core_c=core_c,
                reference_cj=reference_cj,
                level=level,
                csmith_profile=csmith_profile,
                features=features,
                note=note,
            )
        )
    return pairs


def select_pairs(
    pairs: Iterable[ManualPair],
    requested_features: Iterable[str] = (),
    *,
    max_pairs: int = 3,
) -> list[ManualPair]:
    requested = {x for x in requested_features if x}
    selected: list[ManualPair] = []

    for pair in pairs:
        pair_features = set(pair.features)
        if requested and pair_features.isdisjoint(requested):
            continue
        selected.append(pair)
        if len(selected) >= max_pairs:
            break

    if selected or requested:
        return selected

    for pair in pairs:
        selected.append(pair)
        if len(selected) >= max_pairs:
            break
    return selected


def build_pair_prompt_context(
    root: Path,
    requested_features: Iterable[str] = (),
    *,
    max_pairs: int = 3,
    max_chars_per_file: int = 5000,
) -> str:
    pairs = select_pairs(load_pairs(root), requested_features, max_pairs=max_pairs)
    if not pairs:
        return ""

    blocks = [
        "Manual C-to-Cangjie reference pairs follow. Treat them as style and semantic examples; do not copy unrelated code."
    ]
    for idx, pair in enumerate(pairs, 1):
        core = pair.core_c.read_text(encoding="utf-8", errors="replace")[:max_chars_per_file]
        cj = pair.reference_cj.read_text(encoding="utf-8", errors="replace")[:max_chars_per_file]
        rel = pair.case_dir.as_posix()
        feature_text = ", ".join(pair.features) if pair.features else "(unlabeled)"
        blocks.append(
            f"\n[PAIR {idx}: {rel}]\n"
            f"level: {pair.level}\n"
            f"csmith_profile: {pair.csmith_profile}\n"
            f"features: {feature_text}\n"
            f"note: {pair.note}\n"
            f"C core:\n```c\n{core}\n```\n"
            f"Cangjie reference:\n```cangjie\n{cj}\n```"
        )

    return "\n".join(blocks)

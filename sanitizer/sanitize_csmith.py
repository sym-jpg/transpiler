#!/usr/bin/env python3

import argparse
import json
import re
from pathlib import Path


def remove_csmith_include(code: str) -> str:
    return re.sub(
        r'^\s*#\s*include\s+"csmith\.h"\s*\n',
        "",
        code,
        flags=re.MULTILINE,
    )

def extract_checksum_vars(code: str) -> list[tuple[str, str]]:
    return re.findall(
        r'transparent_crc\s*\(\s*([A-Za-z_]\w*(?:\s*\[[^\]]+\])*)\s*,\s*"([^"]+)"',
        code,
    )

def remove_main_function(code: str) -> str:
    m = re.search(r'\bint\s+main\s*\([^)]*\)\s*\{', code)
    if not m:
        return code
    start = m.start()
    brace_start = code.find("{", m.end() - 1)
    if brace_start == -1:
        raise ValueError("found main declaration but no opening brace")
    depth = 0
    i = brace_start
    while i < len(code):
        ch = code[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                return code[:start] + "\n" + code[end:]
        i += 1

    raise ValueError("failed to match braces for main function")


def normalize_stdint_types(code: str) -> str:
    replacements = {
        "int8_t": "int",
        "int16_t": "int",
        "int32_t": "int",
        "int64_t": "long long",

        "uint8_t": "unsigned int",
        "uint16_t": "unsigned int",
        "uint32_t": "unsigned int",
        "uint64_t": "unsigned long long",
    }

    for src, dst in replacements.items():
        code = re.sub(rf"\b{src}\b", dst, code)

    return code



def remove_forward_decls(code: str) -> str:
    return re.sub(
        r'^\s*static\s+(?:unsigned\s+)?(?:int|long\s+long|unsigned\s+long\s+long)\s+func_\d+\s*\([^;{}]*\)\s*;\s*\n',
        "",
        code,
        flags=re.MULTILINE,
    )


def remove_static_keyword(code: str) -> str:
    return re.sub(r"\bstatic\s+", "", code)


def sanitize_csmith(raw_code: str) -> tuple[str, list[tuple[str, str]]]:
    checksum_vars = extract_checksum_vars(raw_code)

    code = raw_code
    code = remove_csmith_include(code)
    code = remove_main_function(code)
    code = remove_forward_decls(code)
    code = normalize_stdint_types(code)
    code = remove_static_keyword(code)

    code = re.sub(r"\n{3,}", "\n\n", code).strip() + "\n"

    return code, checksum_vars


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Raw Csmith C file, e.g. raw.c")
    parser.add_argument("--out-c", default="core.c", help="Sanitized C output")
    parser.add_argument("--out-meta", default="checksum_vars.json", help="Checksum metadata JSON")
    args = parser.parse_args()

    raw_path = Path(args.input)
    raw_code = raw_path.read_text(encoding="utf-8")

    core_code, checksum_vars = sanitize_csmith(raw_code)

    Path(args.out_c).write_text(core_code, encoding="utf-8")
    Path(args.out_meta).write_text(
        json.dumps(
            {
                "checksum_vars": checksum_vars,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"[sanitize] wrote C core to {args.out_c}")
    print(f"[sanitize] wrote checksum vars to {args.out_meta}")
    print(f"[sanitize] checksum vars: {[name for name, _ in checksum_vars]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

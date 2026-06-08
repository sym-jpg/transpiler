import re
from pathlib import Path

INCLUDE_RE = re.compile(r'^\s*#\s*include\s*"csmith\.h"\s*$', re.MULTILINE)
SINK_RE = re.compile(r'^\s*volatile\s+uint64_t\s+csmith_sink_\s*=\s*0\s*;\s*$', re.MULTILINE)

# word-boundary 替换，避免误伤比如 myint32_t_x
INT32_RE = re.compile(r'\bint32_t\b')
UINT32_RE = re.compile(r'\buint32_t\b')

# main 函数头：int main (...) {  （允许多空格/换行）
MAIN_HEAD_RE = re.compile(r'\bint\s+main\s*\([^)]*\)\s*\{', re.MULTILINE)

def remove_main_function(src: str) -> str:
    """
    Remove the first occurrence of `int main(...) { ... }` using brace matching.
    If not found, return src unchanged.
    """
    m = MAIN_HEAD_RE.search(src)
    if not m:
        return src

    start = m.start()
    i = m.end() - 1  # position at '{'
    depth = 0
    n = len(src)

    # Walk forward to find the matching closing brace.
    while i < n:
        ch = src[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i + 1  # include this '}'
                # Also remove trailing whitespace/newlines after main for cleanliness
                tail = src[end:]
                tail = re.sub(r'^\s*\n', '', tail, count=1)
                return src[:start].rstrip() + "\n\n" + tail.lstrip()
        i += 1

    # If we fail to match braces, do nothing (safer than corrupting file)
    return src

def sanitize_c(src: str) -> str:
    src = INCLUDE_RE.sub('', src)
    src = SINK_RE.sub('', src)
    src = INT32_RE.sub('int', src)
    src = UINT32_RE.sub('unsigned', src)
    src = remove_main_function(src)

    src = re.sub(r'\n{3,}', '\n\n', src)
    return src.strip() + "\n"

def sanitize(input : Path, output : Path):
    raw_dir = input  
    out_dir = output
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(raw_dir.glob("case_*.c"))
    if not files:
        raise SystemExit(f"No files matched: {raw_dir}/case_*.c")

    for p in files:
        text = p.read_text(encoding="utf-8", errors="replace")
        new_text = sanitize_c(text)
        out_path = out_dir / p.name
        out_path.write_text(new_text, encoding="utf-8")
        print(f"[sanitized] {p} -> {out_path}")


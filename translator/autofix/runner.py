from __future__ import annotations
import subprocess
from dataclasses import dataclass

@dataclass
class RunResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int

def run_frontend(abs_path: str) -> RunResult:
    cmd = ["python", "-m", "translator.frontend.clang_frontend", abs_path]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return RunResult(p.returncode == 0, p.stdout, p.stderr, p.returncode)
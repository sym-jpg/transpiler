from __future__ import annotations

import os
from pathlib import Path

from clang import cindex


def configure_libclang() -> None:
    """Use an explicit libclang only when the environment requests one."""
    library_file = os.environ.get("LIBCLANG_FILE", "").strip()
    if library_file:
        cindex.Config.set_library_file(str(Path(library_file).expanduser()))


def clang_parse_args() -> list[str]:
    args = ["-std=c11"]
    include_dir = os.environ.get("CSMITH_INCLUDE", "").strip()
    if include_dir:
        args.extend(["-I", str(Path(include_dir).expanduser())])
    return args

"""Monorepo convenience shim for rag_lib.

Allows `import rag_lib` from the monorepo root despite the project directory
otherwise shadowing the src-layout package.
"""
from __future__ import annotations

from pathlib import Path

_SRC_INIT = Path(__file__).resolve().parent / "src" / "rag_lib" / "__init__.py"
_ROOT_DIR = Path(__file__).resolve().parent
__path__ = [str(_ROOT_DIR), str(_SRC_INIT.parent)]
__file__ = str(_SRC_INIT)

_code = compile(_SRC_INIT.read_text(encoding="utf-8"), str(_SRC_INIT), "exec")
exec(_code, globals(), globals())

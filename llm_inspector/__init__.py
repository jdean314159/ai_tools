"""Monorepo convenience shim for llm_inspector.

This file makes `import llm_inspector` work from the monorepo root, where the
project directory would otherwise be treated as an empty namespace package and
shadow the real src-layout package.

It is not included in the built wheel; packaged consumers still import the
normal src-based package.
"""
from __future__ import annotations

from pathlib import Path

_SRC_INIT = Path(__file__).resolve().parent / "src" / "llm_inspector" / "__init__.py"
_ROOT_DIR = Path(__file__).resolve().parent
__path__ = [str(_ROOT_DIR), str(_SRC_INIT.parent)]
__file__ = str(_SRC_INIT)

_code = compile(_SRC_INIT.read_text(encoding="utf-8"), str(_SRC_INIT), "exec")
exec(_code, globals(), globals())

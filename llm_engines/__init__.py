"""Monorepo convenience shim for llm_engines.

Makes `import llm_engines` and `from llm_engines.contracts import ...` work from
monorepo root checkouts where the project directory would otherwise shadow the
real installable package.
"""
from __future__ import annotations

from pathlib import Path

_SRC_INIT = Path(__file__).resolve().parent / "llm_engines" / "__init__.py"
_ROOT_DIR = Path(__file__).resolve().parent
__path__ = [str(_ROOT_DIR), str(_SRC_INIT.parent)]
__file__ = str(_SRC_INIT)

_code = compile(_SRC_INIT.read_text(encoding="utf-8"), str(_SRC_INIT), "exec")
exec(_code, globals(), globals())

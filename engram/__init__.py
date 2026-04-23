"""Monorepo convenience shim for engram.

Makes `import engram` work from monorepo root checkouts where the project
folder would otherwise shadow the real installable package.
"""
from __future__ import annotations

from pathlib import Path

_SRC_INIT = Path(__file__).resolve().parent / "engram" / "__init__.py"
_ROOT_DIR = Path(__file__).resolve().parent
__path__ = [str(_ROOT_DIR), str(_SRC_INIT.parent)]
__file__ = str(_SRC_INIT)

_code = compile(_SRC_INIT.read_text(encoding="utf-8"), str(_SRC_INIT), "exec")
exec(_code, globals(), globals())

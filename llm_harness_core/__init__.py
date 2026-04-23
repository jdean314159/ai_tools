"""Monorepo convenience shim for llm_harness_core.

Allows `import llm_harness_core` from the monorepo root despite the src-layout
project directory otherwise shadowing the installable package as a namespace
package.
"""
from __future__ import annotations

from pathlib import Path

_SRC_INIT = Path(__file__).resolve().parent / "src" / "llm_harness_core" / "__init__.py"
_ROOT_DIR = Path(__file__).resolve().parent
__path__ = [str(_ROOT_DIR), str(_SRC_INIT.parent)]
__file__ = str(_SRC_INIT)

_code = compile(_SRC_INIT.read_text(encoding="utf-8"), str(_SRC_INIT), "exec")
exec(_code, globals(), globals())

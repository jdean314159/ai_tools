from __future__ import annotations

from pathlib import Path

_root_dir = Path(__file__).resolve().parent
_pkg_dir = _root_dir / "llm_inspector_ui"
__path__ = [str(_root_dir), str(_pkg_dir)]

from .llm_inspector_ui import artifact_to_operation_result, describe_ui  # noqa: E402

__all__ = [
    "artifact_to_operation_result",
    "describe_ui",
]

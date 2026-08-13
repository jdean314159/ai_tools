from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from llm_inspector.adapters.engram_adapter import EngramAugmenter
from llm_inspector.core.serialize import to_json
from llm_inspector.protocols import AugmentRequest
from llm_inspector.core import Turn


pytestmark = pytest.mark.engram
GOLDEN = Path(__file__).parent / "golden_engram_trace.json"
_TIKTOKEN_AVAILABLE = importlib.util.find_spec("tiktoken") is not None


def _engram_runtime_available() -> bool:
    if importlib.util.find_spec("engram") is None:
        return False
    try:
        from engram.project_memory import ProjectMemory  # noqa: F401
    except Exception:
        return False
    return True


def _normalize(obj: object) -> object:
    """Recursively strip non-deterministic fields.

    - ``id``:        SQLite ROWID / autoincrement; resets with each tmp_path DB.
    - ``timestamp``: wall-clock float; always differs between runs.
    """
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items() if k not in ("id", "timestamp")}
    if isinstance(obj, list):
        return [_normalize(item) for item in obj]
    return obj


def _stable_payload(payload: str) -> str:
    """Parse, normalize, and re-serialize for deterministic comparison."""
    return json.dumps(_normalize(json.loads(payload)), indent=2)


@pytest.mark.xfail(
    not _TIKTOKEN_AVAILABLE,
    reason=(
        "golden uses tiktoken accounting; the documented word-count fallback "
        "produces different token totals"
    ),
    strict=True,
)
def test_engram_trace_sections_order_golden(tmp_path: Path):
    if not _engram_runtime_available():
        pytest.skip("engram not importable with its runtime dependencies")

    aug = EngramAugmenter(base_dir=tmp_path, project_id="default", project_type="programming_assistant")

    req = AugmentRequest(turn=Turn(role="user", text="hello world"), session_id="s1")
    trace = aug.augment(req)

    # enforce section ordering invariants (subset may be missing if empty)
    origins = [s.origin for s in trace.context.sections]
    # must always contain user and prompt
    assert "user" in origins
    assert "prompt" in origins
    # prompt must be last
    assert trace.context.sections[-1].origin == "prompt"

    stable = _stable_payload(to_json(trace))

    if not GOLDEN.exists():
        GOLDEN.write_text(stable, encoding="utf-8")
        assert GOLDEN.exists()
        return

    expected = GOLDEN.read_text(encoding="utf-8")
    assert stable == expected

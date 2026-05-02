from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Keep integration tests runnable from a source checkout without requiring every
# package to be installed into the active virtual environment.
_SOURCE_PATHS = [
    "llm_harness_core/src",
    "llm_engines",
    "llm_inspector",
    "llm_inspector_ui",
    "engram_lite/src",
    "engram",
    "rag_lib/src",
    "agent_lib/src",
]

for relative in _SOURCE_PATHS:
    path = REPO_ROOT / relative
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))

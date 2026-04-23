from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
for rel in ("language_tutor", "engram", "llm_engines", "engram_lite", "llm_inspector", "llm_harness_core"):
    path = REPO_ROOT / rel
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MONOREPO = ROOT.parent
CANDIDATES = [
    ROOT / "src",
    MONOREPO / "llm_harness_core" / "src",
    MONOREPO / "llm_inspector" / "src",
    MONOREPO / "engram_lite" / "src",
    MONOREPO / "llm_engines",
]
for candidate in CANDIDATES:
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

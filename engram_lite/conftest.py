from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
MONOREPO_CORE = ROOT.parent / "llm_harness_core" / "src"
for candidate in (SRC, ROOT, MONOREPO_CORE):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

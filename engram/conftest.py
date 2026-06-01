from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
MONOREPO_CORE = ROOT.parent / "llm_harness_core" / "src"
for candidate in (ROOT, MONOREPO_CORE, SRC):
    text = str(candidate)
    while text in sys.path:
        sys.path.remove(text)
    sys.path.insert(0, text)

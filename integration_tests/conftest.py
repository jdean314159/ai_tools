from __future__ import annotations
import sys
from pathlib import Path

for pkg_dir in ["llm_engines", "engram", "llm_inspector", "engram_lite"]:
    src = Path(__file__).resolve().parent.parent / pkg_dir
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))

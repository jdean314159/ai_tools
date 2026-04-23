from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEARCH_PATHS = [
    ROOT / 'agent_lib' / 'src',
    ROOT / 'engram_lite' / 'src',
    ROOT / 'llm_harness_core' / 'src',
    ROOT / 'llm_inspector' / 'src',
    ROOT / 'rag_lib' / 'src',
    ROOT / 'engram',
    ROOT / 'llm_engines',
    ROOT / 'language_tutor',
    ROOT / 'llm_inspector_ui',
    ROOT,
]

for path in reversed(SEARCH_PATHS):
    path_str = str(path)
    if path.exists() and path_str not in sys.path:
        sys.path.insert(0, path_str)

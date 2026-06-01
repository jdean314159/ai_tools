from __future__ import annotations

import sys
from pathlib import Path


def install_repo_source_paths() -> None:
    """Prefer this checkout's public package sources when run from repo root."""
    repo_root = Path(__file__).resolve().parents[2]
    source_paths = [
        repo_root / "llm_harness_core" / "src",
        repo_root / "llm_engines",
        repo_root / "engram" / "src",
    ]
    for path in reversed(source_paths):
        text = str(path)
        while text in sys.path:
            sys.path.remove(text)
        sys.path.insert(0, text)

    expected_roots = tuple(str(path) for path in source_paths)
    for package_name in ("engram", "llm_engines", "llm_harness_core"):
        module = sys.modules.get(package_name)
        module_file = str(getattr(module, "__file__", "") or "")
        if module is not None and not module_file.startswith(expected_roots):
            for loaded_name in list(sys.modules):
                if loaded_name == package_name or loaded_name.startswith(f"{package_name}."):
                    sys.modules.pop(loaded_name, None)

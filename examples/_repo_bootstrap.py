from __future__ import annotations

import sys
from pathlib import Path


def install_repo_source_paths(
    anchor: Path,
    package_names: tuple[str, ...],
    relative_source_paths: tuple[str, ...],
) -> None:
    """Prefer this checkout's package sources for direct example execution."""
    repo_root = anchor.resolve().parents[2]
    source_paths = tuple(repo_root / path for path in relative_source_paths)
    for path in reversed(source_paths):
        text = str(path)
        while text in sys.path:
            sys.path.remove(text)
        sys.path.insert(0, text)

    expected_roots = tuple(str(path) for path in source_paths)
    for package_name in package_names:
        module = sys.modules.get(package_name)
        module_file = str(getattr(module, "__file__", "") or "")
        if module is not None and not module_file.startswith(expected_roots):
            for loaded_name in tuple(sys.modules):
                if loaded_name == package_name or loaded_name.startswith(
                    f"{package_name}."
                ):
                    sys.modules.pop(loaded_name, None)

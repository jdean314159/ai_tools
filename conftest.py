from __future__ import annotations

# Monorepo pytest bootstrap.
#
# Several packages use src/ layout, while the repo also contains top-level
# directories with the same names. With pytest importlib collection, pytest
# can otherwise create namespace packages such as llm_inspector from the
# top-level test directory before the real package under src/ is imported.

import importlib
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent

_SOURCE_PATHS = [
    _REPO_ROOT / "agent_lib" / "src",
    _REPO_ROOT / "engram_lite" / "src",
    _REPO_ROOT / "llm_harness_core" / "src",
    _REPO_ROOT / "llm_inspector" / "src",
    _REPO_ROOT / "rag_lib" / "src",
    _REPO_ROOT / "engram",
    _REPO_ROOT / "llm_engines",
    _REPO_ROOT / "language_tutor",
    _REPO_ROOT / "llm_inspector_ui" / "src",
    _REPO_ROOT,
]

_SOURCE_VALUES = [str(_path) for _path in _SOURCE_PATHS]

for _value in reversed(_SOURCE_VALUES):
    if _value in sys.path:
        sys.path.remove(_value)
    sys.path.insert(0, _value)

_existing_pythonpath = [
    _entry
    for _entry in os.environ.get("PYTHONPATH", "").split(os.pathsep)
    if _entry
]
_EXPORTED_PYTHONPATH = [
    *_SOURCE_VALUES,
    *[_entry for _entry in _existing_pythonpath if _entry not in _SOURCE_VALUES],
]
os.environ["PYTHONPATH"] = os.pathsep.join(_EXPORTED_PYTHONPATH)

importlib.invalidate_caches()

_SRC_LAYOUT_PACKAGES = {
    "agent_lib": (
        _REPO_ROOT / "agent_lib" / "src" / "agent_lib",
        _REPO_ROOT / "agent_lib",
    ),
    "engram_lite": (
        _REPO_ROOT / "engram_lite" / "src" / "engram_lite",
        _REPO_ROOT / "engram_lite",
    ),
    "llm_harness_core": (
        _REPO_ROOT / "llm_harness_core" / "src" / "llm_harness_core",
        _REPO_ROOT / "llm_harness_core",
    ),
    "llm_inspector": (
        _REPO_ROOT / "llm_inspector" / "src" / "llm_inspector",
        _REPO_ROOT / "llm_inspector",
    ),
    "rag_lib": (
        _REPO_ROOT / "rag_lib" / "src" / "rag_lib",
        _REPO_ROOT / "rag_lib",
    ),
    "llm_inspector_ui": (
        _REPO_ROOT / "llm_inspector_ui" / "src" / "llm_inspector_ui",
        _REPO_ROOT / "llm_inspector_ui",
    ),
}


def _remove_loaded_package_tree(package_name: str) -> None:
    for key in list(sys.modules):
        if key == package_name or key.startswith(package_name + "."):
            sys.modules.pop(key, None)


def _module_file(module: object) -> str:
    return str(getattr(module, "__file__", "") or "")


def _force_src_layout_package(package_name: str, package_dir: Path, repo_package_dir: Path) -> None:
    init_file = package_dir / "__init__.py"
    if not init_file.exists():
        return

    desired_file_prefix = str(package_dir)
    loaded = sys.modules.get(package_name)

    if loaded is not None:
        loaded_file = _module_file(loaded)
        loaded_path = list(getattr(loaded, "__path__", []) or [])
        loaded_from_src = (
            loaded_file.startswith(desired_file_prefix)
            or str(package_dir) in loaded_path
        )
        if not loaded_from_src:
            _remove_loaded_package_tree(package_name)

    module = importlib.import_module(package_name)

    package_path = getattr(module, "__path__", None)
    if package_path is not None:
        ordered = [str(package_dir), str(repo_package_dir)]
        for value in list(package_path):
            if value not in ordered:
                ordered.append(value)
        module.__path__ = ordered


for _package_name, (_package_dir, _repo_package_dir) in _SRC_LAYOUT_PACKAGES.items():
    _force_src_layout_package(_package_name, _package_dir, _repo_package_dir)


def pytest_addoption(parser: object) -> None:
    parser.addoption(
        "--run-engram",
        action="store_true",
        default=False,
        help="Run tests marked 'engram' that require optional Engram runtime dependencies.",
    )


def pytest_collection_modifyitems(config: object, items: list[object]) -> None:
    run_engram = bool(getattr(config, "getoption")("--run-engram", default=False)) or bool(
        os.environ.get("AI_TOOLS_RUN_ENGRAM_TESTS")
    )
    if run_engram:
        return

    skip_engram = pytest.mark.skip(
        reason="Engram integration tests disabled — run with --run-engram or AI_TOOLS_RUN_ENGRAM_TESTS=1"
    )
    for item in items:
        if "engram" in getattr(item, "keywords", {}):
            item.add_marker(skip_engram)

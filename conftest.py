from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent

# Transitional monorepo test bootstrap.
#
# This is intentionally centralized here. Do not add package-local
# sys.path inserts or package-specific import loaders in subproject
# conftest.py files.
#
# The purpose is to keep repo-root pytest collection deterministic while
# the repo still has same-named outer project directories such as
# llm_inspector/, rag_lib/, and llm_inspector_ui/.
TEST_SOURCE_PATHS = [
    REPO_ROOT / "llm_harness_core" / "src",
    REPO_ROOT / "llm_engines" / "src",
    REPO_ROOT / "reasoning_loop_guard" / "src",
    REPO_ROOT / "action_trajectory_loop_guard" / "src",
    REPO_ROOT / "engram" / "src",
    REPO_ROOT / "llm_inspector" / "src",
    REPO_ROOT / "rag_lib" / "src",
    REPO_ROOT / "llm_inspector_ui" / "src",
    REPO_ROOT / "agent_lib" / "src",
    REPO_ROOT / "examples" / "language_tutor_reference_app" / "src",
    REPO_ROOT / "examples" / "diagnostics_agent" / "src",
]

SOURCE_PACKAGE_EXPECTATIONS = {
    "llm_harness_core": REPO_ROOT / "llm_harness_core" / "src" / "llm_harness_core",
    "llm_engines": REPO_ROOT / "llm_engines" / "src" / "llm_engines",
    "reasoning_loop_guard": (
        REPO_ROOT / "reasoning_loop_guard" / "src" / "reasoning_loop_guard"
    ),
    "action_trajectory_loop_guard": (
        REPO_ROOT / "action_trajectory_loop_guard" / "src" / "action_trajectory_loop_guard"
    ),
    "llm_inspector": REPO_ROOT / "llm_inspector" / "src" / "llm_inspector",
    "rag_lib": REPO_ROOT / "rag_lib" / "src" / "rag_lib",
    "llm_inspector_ui": REPO_ROOT / "llm_inspector_ui" / "src" / "llm_inspector_ui",
    "examples.language_tutor": REPO_ROOT / "examples" / "language_tutor",
    "language_tutor": (
        REPO_ROOT / "examples" / "language_tutor_reference_app" / "src" / "language_tutor"
    ),
    "agent_lib": REPO_ROOT / "agent_lib" / "src" / "agent_lib",
    "diagnostics_agent": (
        REPO_ROOT / "examples" / "diagnostics_agent" / "src" / "diagnostics_agent"
    ),
    "mail_lib": REPO_ROOT / "mail_lib",
}


def _install_test_source_paths() -> None:
    installed: list[str] = []
    for path in reversed(TEST_SOURCE_PATHS):
        if not path.exists():
            continue
        text = str(path)
        while text in sys.path:
            sys.path.remove(text)
        sys.path.insert(0, text)
        installed.append(text)

    existing_pythonpath = [
        item for item in os.environ.get("PYTHONPATH", "").split(os.pathsep) if item
    ]
    exported: list[str] = []
    for text in reversed(installed):
        if text not in exported:
            exported.append(text)
    for text in existing_pythonpath:
        if text not in exported:
            exported.append(text)
    os.environ["PYTHONPATH"] = os.pathsep.join(exported)


def _module_location(module: object) -> Path | None:
    file_value = getattr(module, "__file__", None)
    if file_value:
        return Path(file_value).resolve()

    path_value = getattr(module, "__path__", None)
    if path_value:
        values = list(path_value)
        if values:
            return Path(values[0]).resolve()

    return None


def _location_is_under(location: Path | None, expected_dir: Path) -> bool:
    if location is None:
        return False

    expected = expected_dir.resolve()
    location = location.resolve()

    return location == expected or expected in location.parents


def _drop_package(name: str) -> None:
    for module_name in list(sys.modules):
        if module_name == name or module_name.startswith(f"{name}."):
            sys.modules.pop(module_name, None)


def _anchor_source_packages() -> None:
    # Temporary protection against repo-root namespace shadowing during
    # pytest collection. This is centralized and should be removable
    # after all packages use src layout and package-local import hacks
    # are gone.
    for package_name, expected_dir in SOURCE_PACKAGE_EXPECTATIONS.items():
        loaded = sys.modules.get(package_name)
        if loaded is not None and not _location_is_under(_module_location(loaded), expected_dir):
            _drop_package(package_name)

        module = importlib.import_module(package_name)
        location = _module_location(module)

        if not _location_is_under(location, expected_dir):
            raise ImportError(
                f"{package_name!r} resolved to {location}, expected under {expected_dir}"
            )


_install_test_source_paths()
_anchor_source_packages()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-engram",
        action="store_true",
        default=False,
        help="Run tests marked 'engram'. These may require ChromaDB/local memory state.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "engram: tests requiring engram/chromadb/local memory stack",
    )
    config.addinivalue_line(
        "markers",
        "integration: cross-package integration tests",
    )
    config.addinivalue_line(
        "markers",
        "rag: tests requiring rag_lib integration",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    run_engram = config.getoption("--run-engram") or os.environ.get(
        "AI_TOOLS_RUN_ENGRAM_TESTS"
    ) == "1"

    if run_engram:
        return

    skip_engram = pytest.mark.skip(
        reason="requires --run-engram or AI_TOOLS_RUN_ENGRAM_TESTS=1"
    )

    for item in items:
        if "engram" in item.keywords:
            item.add_marker(skip_engram)

from __future__ import annotations

import importlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


PACKAGE_EXPECTATIONS = {
    "llm_harness_core": REPO_ROOT / "llm_harness_core" / "src" / "llm_harness_core",
    "llm_inspector": REPO_ROOT / "llm_inspector" / "src" / "llm_inspector",
    "rag_lib": REPO_ROOT / "rag_lib" / "src" / "rag_lib",
    "llm_inspector_ui": REPO_ROOT / "llm_inspector_ui" / "src" / "llm_inspector_ui",
    "agent_lib": REPO_ROOT / "agent_lib" / "src" / "agent_lib",
    "engram": REPO_ROOT / "engram" / "src" / "engram",
    "llm_engines": REPO_ROOT / "llm_engines" / "src" / "llm_engines",
    "examples.language_tutor": REPO_ROOT / "examples" / "language_tutor",
    "mail_lib": REPO_ROOT / "mail_lib",
}


MODULE_EXPECTATIONS = {
    "llm_inspector.rag": REPO_ROOT / "llm_inspector" / "src" / "llm_inspector" / "rag.py",
    "rag_lib.pipeline": REPO_ROOT / "rag_lib" / "src" / "rag_lib" / "pipeline.py",
    "llm_inspector_ui.utils.trace_access": (
        REPO_ROOT
        / "llm_inspector_ui"
        / "src"
        / "llm_inspector_ui"
        / "utils"
        / "trace_access.py"
    ),
}


def _module_location(module: object) -> Path:
    file_value = getattr(module, "__file__", None)
    if file_value:
        return Path(file_value).resolve()

    path_value = getattr(module, "__path__", None)
    if path_value:
        values = list(path_value)
        if values:
            return Path(values[0]).resolve()

    raise AssertionError(f"No import location for module {module!r}")


def _assert_under(module_name: str, expected_dir: Path) -> None:
    module = importlib.import_module(module_name)
    location = _module_location(module)
    expected = expected_dir.resolve()

    assert location == expected or expected in location.parents, (
        f"{module_name} resolved to {location}, expected under {expected}"
    )


def _assert_file(module_name: str, expected_file: Path) -> None:
    module = importlib.import_module(module_name)
    location = _module_location(module)

    assert location == expected_file.resolve(), (
        f"{module_name} resolved to {location}, expected {expected_file.resolve()}"
    )


def test_package_import_provenance() -> None:
    for module_name, expected_dir in PACKAGE_EXPECTATIONS.items():
        _assert_under(module_name, expected_dir)


def test_cross_package_module_import_provenance() -> None:
    for module_name, expected_file in MODULE_EXPECTATIONS.items():
        _assert_file(module_name, expected_file)

from __future__ import annotations

from pathlib import Path

from examples._repo_bootstrap import install_repo_source_paths as _install


def install_repo_source_paths() -> None:
    _install(
        Path(__file__),
        package_names=("llm_engines", "llm_harness_core"),
        relative_source_paths=(
            "llm_harness_core/src",
            "llm_engines/src",
        ),
    )

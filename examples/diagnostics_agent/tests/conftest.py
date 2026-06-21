from __future__ import annotations

import subprocess
from shutil import which

import pytest

from diagnostics_agent import SandboxConfig


@pytest.fixture
def require_sandbox_runtime() -> None:
    config = SandboxConfig()
    if which(config.runtime) is None:
        pytest.skip(f"{config.runtime} is not installed")

    image_check = subprocess.run(
        [config.runtime, "image", "exists", config.image],
        capture_output=True,
        text=True,
        check=False,
    )
    if image_check.returncode != 0:
        pytest.skip(f"{config.runtime} image is not available locally: {config.image}")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--gate-model",
        default="qwen3.6:27b",
        help="Ollama model used by the diagnostics false-positive gate.",
    )
    parser.addoption(
        "--gate-base-url",
        default=None,
        help="Ollama base URL used by the diagnostics false-positive gate.",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    if "ollama" in (config.option.markexpr or ""):
        return

    skip_live = pytest.mark.skip(reason="requires explicit -m ollama selection")
    for item in items:
        if item.get_closest_marker("ollama") is not None:
            item.add_marker(skip_live)

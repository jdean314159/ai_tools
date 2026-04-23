from __future__ import annotations

import asyncio

import pytest

from language_tutor.routes import session as session_routes


def test_reference_stack_default_descriptor_is_teaching_oriented():
    response = asyncio.run(session_routes.get_reference_stack())
    assert response.app == "language_tutor"
    assert response.learning_stage.startswith("Stage 5")
    assert "llm_engines" in response.required_packages
    assert "llm_inspector" in response.observability_packages
    assert response.memory_backend == "engram_lite"
    assert response.capability["provider"] == "language_tutor"
    assert "memory_backend:engram_lite" in response.capability["features"]


@pytest.mark.parametrize("backend", ["engram_lite", "engram"])
def test_reference_stack_supports_both_memory_backends(backend: str):
    response = asyncio.run(session_routes.get_reference_stack(memory_backend=backend))
    assert response.memory_backend == backend
    assert response.current_paths["memory_layer"].startswith(backend)
    assert f"memory_backend:{backend}" in response.capability["features"]

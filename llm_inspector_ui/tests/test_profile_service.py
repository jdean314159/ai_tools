from __future__ import annotations

import pytest

from llm_inspector_ui.services.profile_service import ProfileService
from llm_inspector_ui.state.session_store import SessionStore


def test_profile_service_crud(tmp_path):
    store = SessionStore(tmp_path / "workbench.sqlite")
    service = ProfileService(store)

    created = service.create_profile(
        name="Engram Test",
        engine_id="echo",
        model_id="echo",
        augmenter_ids=["engram"],
        engine_settings={"temperature": 0.1},
        augmenter_options={
            "baseline": {"system_prompt": "Be concise."},
            "engram": {"project_id": "demo", "project_type": "programming_assistant"},
        },
        max_prompt_tokens=2048,
    )
    assert created.name == "Engram Test"
    assert created.augmenter_ids == ["engram"]
    assert created.augmenter_options["baseline"]["system_prompt"] == "Be concise."

    updated = service.update_profile(
        created.profile_id,
        name="Engram Test 2",
        augmenter_ids=["baseline", "engram"],
        tags=["demo"],
        augmenter_options={
            "baseline": {"system_prompt": "System prompt"},
            "engram": {"project_id": "demo2"},
        },
    )
    assert updated.name == "Engram Test 2"
    assert updated.augmenter_ids == ["baseline", "engram"]
    assert updated.tags == ["demo"]
    assert updated.augmenter_options["engram"]["project_id"] == "demo2"

    duplicate = service.duplicate_profile(created.profile_id)
    assert duplicate.profile_id != created.profile_id
    assert duplicate.name.endswith("(copy)")
    assert duplicate.augmenter_options["baseline"]["system_prompt"] == "System prompt"

    duplicate.augmenter_options["baseline"]["system_prompt"] = "Changed in duplicate"
    reloaded_original = service.get_profile(created.profile_id)
    assert reloaded_original is not None
    assert reloaded_original.augmenter_options["baseline"]["system_prompt"] == "System prompt"

    profiles = service.list_profiles()
    assert len(profiles) == 2

    service.delete_profile(created.profile_id)
    assert service.get_profile(created.profile_id) is None


def test_profile_service_rejects_unknown_fields(tmp_path):
    store = SessionStore(tmp_path / "workbench.sqlite")
    service = ProfileService(store)

    created = service.create_profile(
        name="Baseline",
        engine_id="echo",
        model_id="echo",
    )

    with pytest.raises(ValueError):
        service.update_profile(created.profile_id, unknown_field=123)

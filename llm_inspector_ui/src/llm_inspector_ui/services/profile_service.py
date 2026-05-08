from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any, Optional
from uuid import uuid4

from llm_inspector_ui.state.models import WorkbenchProfile
from llm_inspector_ui.state.session_store import SessionStore


class ProfileService:
    def __init__(self, session_store: SessionStore):
        self.session_store = session_store

    def list_profiles(self) -> list[WorkbenchProfile]:
        return self.session_store.list_profiles()

    def get_profile(self, profile_id: str) -> Optional[WorkbenchProfile]:
        return self.session_store.get_profile(profile_id)

    def create_profile(
        self,
        *,
        name: str,
        engine_id: str,
        model_id: str | None,
        augmenter_ids: list[str] | None = None,
        engine_config: dict[str, Any] | None = None,
        engine_settings: dict[str, Any] | None = None,
        augmenter_options: dict[str, dict[str, Any]] | None = None,
        max_prompt_tokens: int | None = None,
        reserve_output_tokens: int = 512,
        tags: list[str] | None = None,
    ) -> WorkbenchProfile:
        profile = WorkbenchProfile(
            profile_id=str(uuid4()),
            name=name,
            engine_id=engine_id,
            model_id=model_id,
            augmenter_ids=list(augmenter_ids or ["baseline"]),
            engine_config=dict(engine_config or {}),
            engine_settings=dict(engine_settings or {}),
            augmenter_options={
                str(key): dict(value or {}) for key, value in (augmenter_options or {}).items()
            },
            max_prompt_tokens=max_prompt_tokens,
            reserve_output_tokens=reserve_output_tokens,
            tags=list(tags or []),
        )
        self.session_store.save_profile(profile)
        return profile

    def update_profile(self, profile_id: str, **changes: Any) -> WorkbenchProfile:
        profile = self.session_store.get_profile(profile_id)
        if profile is None:
            raise KeyError(f"Profile not found: {profile_id}")

        allowed = {
            "name",
            "engine_id",
            "model_id",
            "augmenter_ids",
            "engine_config",
            "engine_settings",
            "augmenter_options",
            "max_prompt_tokens",
            "reserve_output_tokens",
            "tags",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unknown profile fields: {sorted(unknown)}")

        normalized = dict(changes)
        if "augmenter_ids" in normalized and normalized["augmenter_ids"] is not None:
            normalized["augmenter_ids"] = list(normalized["augmenter_ids"])
        if "engine_config" in normalized and normalized["engine_config"] is not None:
            normalized["engine_config"] = copy.deepcopy(normalized["engine_config"])
        if "engine_settings" in normalized and normalized["engine_settings"] is not None:
            normalized["engine_settings"] = copy.deepcopy(normalized["engine_settings"])
        if "augmenter_options" in normalized and normalized["augmenter_options"] is not None:
            normalized["augmenter_options"] = {
                str(key): copy.deepcopy(value or {})
                for key, value in normalized["augmenter_options"].items()
            }
        if "tags" in normalized and normalized["tags"] is not None:
            normalized["tags"] = list(normalized["tags"])

        updated = replace(profile, **normalized)
        self.session_store.save_profile(updated)
        return updated

    def duplicate_profile(self, profile_id: str, *, new_name: str | None = None) -> WorkbenchProfile:
        profile = self.session_store.get_profile(profile_id)
        if profile is None:
            raise KeyError(f"Profile not found: {profile_id}")

        duplicate = replace(
            profile,
            profile_id=str(uuid4()),
            name=new_name or f"{profile.name} (copy)",
            augmenter_ids=list(profile.augmenter_ids),
            engine_config=copy.deepcopy(profile.engine_config),
            engine_settings=copy.deepcopy(profile.engine_settings),
            augmenter_options=copy.deepcopy(profile.augmenter_options),
            tags=list(profile.tags),
        )
        self.session_store.save_profile(duplicate)
        return duplicate

    def delete_profile(self, profile_id: str) -> None:
        self.session_store.delete_profile(profile_id)

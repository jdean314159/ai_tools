from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class ChatSession:
    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatTurn:
    turn_id: str
    session_id: str
    role: str
    text: str
    created_at: datetime
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunArtifact:
    run_id: str
    session_id: str
    turn_id: str
    assistant_turn_id: Optional[str]
    created_at: datetime

    engine_id: str
    model_id: Optional[str]
    augmenter_id: str
    mode: str  # "chat" | "compare"
    status: str = "ok"  # "ok" | "error" | "skipped"

    user_text: str = ""
    prompt: str = ""
    response_text: str = ""

    trace: Any = None
    engine_metrics: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class WorkbenchProfile:
    profile_id: str
    name: str

    engine_id: str
    model_id: Optional[str]

    augmenter_ids: list[str] = field(default_factory=lambda: ["baseline"])
    engine_config: dict[str, Any] = field(default_factory=dict)
    engine_settings: dict[str, Any] = field(default_factory=dict)
    augmenter_options: dict[str, dict[str, Any]] = field(default_factory=dict)

    max_prompt_tokens: Optional[int] = None
    reserve_output_tokens: int = 512

    tags: list[str] = field(default_factory=list)

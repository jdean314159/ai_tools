from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class TutorMemoryBackend(Protocol):
    backend_name: str
    helpers: Any | None
    semantic: Any | None

    def add_turn(self, role: str, text: str) -> None: ...
    def build_prompt(self, user_message: str, **kwargs: Any) -> dict[str, Any]: ...
    def search_episodes(
        self, query: str, n: int = 5, min_importance: float = 0.0, days_back: int | None = None
    ) -> list[Any]: ...
    def get_recent_turns(self, n: int = 10) -> list[Any]: ...
    def store_episode(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
        bypass_filter: bool = False,
    ) -> Any: ...
    def index_text(self, text: str) -> Any: ...
    def run_lifecycle_maintenance(self) -> Any: ...
    def get_stats(self) -> dict[str, Any]: ...
    def close(self) -> None: ...


@dataclass
class _NormalizedTurn:
    role: str
    content: str


class EngramTutorMemory:
    """Adapt the current public Engram API to the tutor memory protocol."""

    backend_name = "engram"

    def __init__(self, memory: Any, session_id: str) -> None:
        self._memory = memory
        self.session_id = session_id

    @property
    def helpers(self) -> Any | None:
        return getattr(self._memory, "helpers", None)

    @property
    def semantic(self) -> Any | None:
        return getattr(self._memory, "semantic", None)

    def add_turn(self, role: str, text: str) -> None:
        self._memory.add_turn(role, text, self.session_id)

    def build_prompt(self, user_message: str, **kwargs: Any) -> dict[str, Any]:
        return self._memory.build_prompt(user_message=user_message, **kwargs)

    def search_episodes(
        self,
        query: str,
        n: int = 5,
        min_importance: float = 0.0,
        days_back: int | None = None,
    ) -> list[Any]:
        del days_back
        return self._memory.search_episodes(query=query, n=n, min_importance=min_importance)

    def get_recent_turns(self, n: int = 10) -> list[Any]:
        turns = self._memory.get_recent_turns(self.session_id, limit=n)
        return [
            _NormalizedTurn(
                role=str(turn.get("role", "unknown")),
                content=str(turn.get("text", "")),
            )
            for turn in turns
        ]

    def store_episode(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
        bypass_filter: bool = False,
    ) -> Any:
        return self._memory.store_episode(
            text=text,
            metadata=metadata,
            importance=importance,
            bypass_filter=bypass_filter,
        )

    def index_text(self, text: str) -> Any:
        return self._memory.index_text(text)

    def run_lifecycle_maintenance(self) -> Any:
        return self._memory.run_lifecycle_maintenance()

    def get_stats(self) -> dict[str, Any]:
        return self._memory.get_stats()

    def close(self) -> None:
        self._memory.close()


def create_memory_backend(
    *,
    backend_name: str,
    language: str,
    base_dir: Path,
    session_id: str,
    memory_engine: Any = None,
    total_prompt_tokens: int = 4096,
) -> TutorMemoryBackend:
    backend = (backend_name or "engram").strip().lower()

    token_counter = getattr(memory_engine, "count_tokens", None)
    if token_counter is not None and not callable(token_counter):
        token_counter = None

    if backend == "engram":
        from engram import ProjectMemory, ProjectType

        memory = ProjectMemory(
            project_id=f"{language}_tutor",
            project_type=ProjectType.LANGUAGE_TUTOR,
            base_dir=base_dir / "memory",
            session_id=session_id,
            llm_engine=memory_engine,
            total_prompt_tokens=total_prompt_tokens,
            token_counter=token_counter,
        )
        return EngramTutorMemory(memory, session_id=session_id)

    raise ValueError(f"Unsupported memory backend '{backend_name}'. Expected 'engram'.")

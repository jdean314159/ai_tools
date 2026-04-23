from __future__ import annotations

from typing import Iterable

from agent_lib.coordination import (
    ExternalAgentSession,
    ExternalAgentTeam,
    ExternalSessionCoordinator,
    InMemoryMailbox,
)


def make_external_programming_team(
    *,
    project_id: str,
    mentor_id: str = "mentor",
    worker_ids: Iterable[str] = ("worker",),
    critic_id: str | None = None,
    scout_ids: Iterable[str] = (),
    shared_memory_backend: str = "engram_lite",
) -> ExternalAgentTeam:
    mentor = ExternalAgentSession(agent_id=mentor_id, role="mentor", runtime="external-session")
    workers = [ExternalAgentSession(agent_id=agent_id, role="worker", runtime="external-session") for agent_id in worker_ids]
    critic = None
    if critic_id:
        critic = ExternalAgentSession(agent_id=critic_id, role="critic", runtime="external-session")
    scouts = [ExternalAgentSession(agent_id=agent_id, role="scout", runtime="external-session") for agent_id in scout_ids]
    return ExternalAgentTeam(
        project_id=project_id,
        mentor=mentor,
        workers=workers,
        critic=critic,
        scouts=scouts,
        shared_memory_backend=shared_memory_backend,
    )


def make_external_session_coordinator(team: ExternalAgentTeam | None = None) -> ExternalSessionCoordinator:
    coordinator = ExternalSessionCoordinator(InMemoryMailbox())
    if team is not None:
        coordinator.register_team(team)
    return coordinator

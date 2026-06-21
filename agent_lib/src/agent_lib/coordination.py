from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Literal, Protocol, Sequence
from uuid import uuid4

MessageKind = Literal[
    "finding",
    "question",
    "handoff",
    "patch_proposal",
    "verification_result",
    "escalation_request",
    "decision",
]

ReservationStatus = Literal["active", "released", "conflict"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ExternalAgentSession:
    agent_id: str
    role: str
    runtime: str = "external"
    workspace: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CoordinationMessage:
    sender: str
    recipient: str
    kind: MessageKind
    subject: str
    body: str
    thread_id: str = "default"
    message_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FileReservation:
    path: str
    holder: str
    thread_id: str = "default"
    status: ReservationStatus = "active"
    note: str = ""
    created_at: datetime | None = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionMailbox(Protocol):
    def register(self, session: ExternalAgentSession) -> None: ...
    def send(self, message: CoordinationMessage) -> None: ...
    def fetch_inbox(self, recipient: str, *, thread_id: str | None = None) -> list[CoordinationMessage]: ...
    def reserve_paths(
        self,
        holder: str,
        paths: Sequence[str],
        *,
        thread_id: str = "default",
        note: str = "",
    ) -> list[FileReservation]: ...
    def release_paths(self, holder: str, paths: Sequence[str]) -> list[FileReservation]: ...
    def active_reservations(self, *, thread_id: str | None = None) -> list[FileReservation]: ...


class InMemoryMailbox:
    def __init__(self, isolation_manager: Any | None = None) -> None:
        self._sessions: dict[str, ExternalAgentSession] = {}
        self._messages: list[CoordinationMessage] = []
        self.isolation_manager = isolation_manager
        # This remains the complete source of truth only for legacy no-manager mailboxes.
        self._reservations: dict[str, FileReservation] = {}

    def register(self, session: ExternalAgentSession) -> None:
        self._sessions[session.agent_id] = session

    def send(self, message: CoordinationMessage) -> None:
        if message.sender not in self._sessions:
            self.register(ExternalAgentSession(agent_id=message.sender, role="unknown"))
        if message.recipient not in self._sessions:
            self.register(ExternalAgentSession(agent_id=message.recipient, role="unknown"))
        self._messages.append(message)

    def fetch_inbox(self, recipient: str, *, thread_id: str | None = None) -> list[CoordinationMessage]:
        out = [m for m in self._messages if m.recipient == recipient]
        if thread_id is not None:
            out = [m for m in out if m.thread_id == thread_id]
        return list(out)

    def reserve_paths(
        self,
        holder: str,
        paths: Sequence[str],
        *,
        thread_id: str = "default",
        note: str = "",
    ) -> list[FileReservation]:
        if self.isolation_manager is not None:
            return [
                self._reserve_managed_path(holder, raw_path, thread_id=thread_id, note=note)
                for raw_path in paths
            ]
        results: list[FileReservation] = []
        for raw_path in paths:
            path = str(raw_path)
            current = self._reservations.get(path)
            if current and current.status == "active" and current.holder != holder:
                results.append(
                    FileReservation(
                        path=path,
                        holder=holder,
                        thread_id=thread_id,
                        status="conflict",
                        note=f"Already reserved by {current.holder}.",
                        metadata={"current_holder": current.holder},
                    )
                )
                continue
            reservation = FileReservation(path=path, holder=holder, thread_id=thread_id, status="active", note=note)
            self._reservations[path] = reservation
            results.append(reservation)
        return results

    def _reservation_from_lease(self, path: str, record: dict[str, Any], *, status: ReservationStatus = "active") -> FileReservation:
        created_at = record.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except ValueError:
                created_at = None
        if not isinstance(created_at, datetime):
            created_at = None
        return FileReservation(
            path=path,
            holder=str(record.get("owner_id") or ""),
            thread_id=str(record.get("thread_id") or "default"),
            status=status,
            note=str(record.get("note") or ""),
            created_at=created_at,
            metadata=dict(record.get("metadata") or {}),
        )

    def _reserve_managed_path(self, holder: str, raw_path: str, *, thread_id: str, note: str) -> FileReservation:
        from .programming import _normalize_rel_path

        path = _normalize_rel_path(str(raw_path))
        lease = self.isolation_manager.acquire_patch_lease(holder, [path], thread_id=thread_id, note=note)
        record = self.isolation_manager.patch_lease(path) or {}
        if lease.status == "denied":
            current_holder = str(record.get("owner_id") or "")
            return FileReservation(
                path=path,
                holder=holder,
                thread_id=thread_id,
                status="conflict",
                note=f"Already reserved by {current_holder}.",
                created_at=None,
                metadata={"current_holder": current_holder},
            )
        return self._reservation_from_lease(path, record)

    def release_paths(self, holder: str, paths: Sequence[str]) -> list[FileReservation]:
        if self.isolation_manager is not None:
            released = self.isolation_manager.release_patch_lease(holder, paths)
            reservations: list[FileReservation] = []
            for path in released.released_paths:
                record = self.isolation_manager.patch_lease(path) or {"owner_id": holder}
                reservations.append(self._reservation_from_lease(path, record, status="released"))
            return reservations
        released: list[FileReservation] = []
        for raw_path in paths:
            path = str(raw_path)
            current = self._reservations.get(path)
            if current is None or current.holder != holder or current.status != "active":
                continue
            updated = FileReservation(
                path=current.path,
                holder=current.holder,
                thread_id=current.thread_id,
                status="released",
                note=current.note,
                created_at=current.created_at,
                metadata=dict(current.metadata),
            )
            self._reservations[path] = updated
            released.append(updated)
        return released

    def active_reservations(self, *, thread_id: str | None = None) -> list[FileReservation]:
        if self.isolation_manager is not None:
            reservations = [
                self._reservation_from_lease(path, record)
                for path, record in self.isolation_manager.active_patch_owners().items()
                if record.get("status") == "active"
            ]
            if thread_id is not None:
                reservations = [reservation for reservation in reservations if reservation.thread_id == thread_id]
            return sorted(reservations, key=lambda item: item.path)
        reservations = [r for r in self._reservations.values() if r.status == "active"]
        if thread_id is not None:
            reservations = [r for r in reservations if r.thread_id == thread_id]
        return sorted(reservations, key=lambda item: item.path)


@dataclass
class ExternalAgentTeam:
    project_id: str
    mentor: ExternalAgentSession
    workers: list[ExternalAgentSession]
    critic: ExternalAgentSession | None = None
    scouts: list[ExternalAgentSession] = field(default_factory=list)
    shared_memory_backend: str = "engram"

    @property
    def all_sessions(self) -> list[ExternalAgentSession]:
        sessions = [self.mentor, *self.workers]
        if self.critic is not None:
            sessions.append(self.critic)
        sessions.extend(self.scouts)
        return sessions


def route_by_capability(team: ExternalAgentTeam, required_tool: str) -> ExternalAgentSession | None:
    """Return the first team session granted *required_tool*, or None.

    First-match behavior is intentional. Resolving multiple matching sessions is
    a scheduling policy outside this deterministic control-plane primitive.
    """
    return next(
        (session for session in team.all_sessions if required_tool in session.capabilities),
        None,
    )


def build_session_tool_runtime(
    session: ExternalAgentSession,
    inner: Any,
    workspace: Any,
    *,
    root: str,
    isolation_manager: Any | None = None,
) -> Any:
    """Build a runtime whose tool grant exactly matches a session's capabilities."""
    from .programming import EnforcingToolRuntime

    scoped_workspace = replace(workspace, allowed_tools=list(session.capabilities))
    return EnforcingToolRuntime(
        inner,
        scoped_workspace,
        root=root,
        owner_id=session.agent_id,
        isolation_manager=isolation_manager,
    )


def build_coordinator_tool_runtime(
    session: ExternalAgentSession,
    inner: Any,
    workspace: Any,
    *,
    root: str,
    isolation_manager: Any | None = None,
) -> Any:
    """Build a coordinator runtime with an explicit deny-all tool grant."""
    from .programming import EnforcingToolRuntime

    scoped_workspace = replace(workspace, allowed_tools=[])
    return EnforcingToolRuntime(
        inner,
        scoped_workspace,
        root=root,
        owner_id=session.agent_id,
        isolation_manager=isolation_manager,
    )


@dataclass(frozen=True)
class ManagedCoordination:
    coordinator: "ExternalSessionCoordinator"
    isolation_manager: Any
    worker_runtimes: dict[str, Any]


def build_managed_coordination(
    team: ExternalAgentTeam,
    inner: Any,
    workspace: Any,
    *,
    root: str,
    state_root: str,
) -> ManagedCoordination:
    """Construct a manager-backed coordinator and worker runtimes sharing one authority."""
    from .programming import WorkspaceIsolationManager

    manager = WorkspaceIsolationManager(state_root)
    coordinator = ExternalSessionCoordinator(InMemoryMailbox(isolation_manager=manager))
    coordinator.register_team(team)
    worker_runtimes = {
        worker.agent_id: build_session_tool_runtime(
            worker, inner, workspace, root=root, isolation_manager=manager
        )
        for worker in team.workers
    }
    return ManagedCoordination(
        coordinator=coordinator,
        isolation_manager=manager,
        worker_runtimes=worker_runtimes,
    )


class ExternalSessionCoordinator:
    """Lightweight coordination surface for externally orchestrated agent sessions.

    This is intentionally small. It models the integration style used by systems that
    run persistent external agents and coordinate them with messaging plus advisory
    file reservations, without forcing them into the native AgentRuntime loop.
    """

    def __init__(self, mailbox: SessionMailbox | None = None) -> None:
        self.mailbox = mailbox or InMemoryMailbox()

    def register_team(self, team: ExternalAgentTeam) -> ExternalAgentTeam:
        for session in team.all_sessions:
            self.mailbox.register(session)
        return team

    def send(
        self,
        sender: str,
        recipient: str,
        *,
        kind: MessageKind,
        subject: str,
        body: str,
        thread_id: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> CoordinationMessage:
        message = CoordinationMessage(
            sender=sender,
            recipient=recipient,
            kind=kind,
            subject=subject,
            body=body,
            thread_id=thread_id,
            metadata=dict(metadata or {}),
        )
        self.mailbox.send(message)
        return message

    def inbox(self, recipient: str, *, thread_id: str | None = None) -> list[CoordinationMessage]:
        return self.mailbox.fetch_inbox(recipient, thread_id=thread_id)

    def reserve_paths(
        self,
        holder: str,
        paths: Sequence[str],
        *,
        thread_id: str = "default",
        note: str = "",
    ) -> list[FileReservation]:
        return self.mailbox.reserve_paths(holder, paths, thread_id=thread_id, note=note)

    def release_paths(self, holder: str, paths: Sequence[str]) -> list[FileReservation]:
        return self.mailbox.release_paths(holder, paths)

from __future__ import annotations

from typing import Sequence, Any

from llm_inspector import ContextResult, EvidenceItem, RunMetrics, Section, TokenAccounting, Trace, TraceEvent, Turn

from .contracts import AgentMemoryAdapter, AgentStep, AgentTask


def _trace_from_evidence(task: AgentTask, evidence: Sequence[EvidenceItem], *, backend_name: str) -> Trace:
    sections = []
    if evidence:
        grouped: dict[str, list[str]] = {}
        for item in evidence:
            grouped.setdefault(item.source or 'memory', []).append(item.text)
        for origin, items in grouped.items():
            sections.append(Section(title=origin.title(), text="\n".join(items), origin=origin))
    context = ContextResult(
        sections=sections,
        evidence=list(evidence),
        token_accounting=TokenAccounting(total_tokens=sum(max(1, len(item.text.split())) for item in evidence)),
        signals={'memory_backend': backend_name, 'evidence_count': len(evidence)},
    )
    return Trace(
        turn=Turn(role='user', text=task.goal, session_id=task.session_id),
        context=context,
        metrics=RunMetrics(engine=backend_name, model=None),
        events=[TraceEvent(event_type='agent_memory_recall', source_package='agent_lib', source_component='memory', payload={'memory_backend': backend_name, 'evidence_count': len(evidence)}, severity='info', message=f'Recalled {len(evidence)} evidence items from {backend_name}.', tags=('agent','memory'))],
    )


class NullMemoryAdapter:
    backend_name = "null"

    def recall(self, task: AgentTask, steps: Sequence[AgentStep], *, limit: int = 5) -> list[EvidenceItem]:
        return []

    def trace_recall(self, task: AgentTask, steps: Sequence[AgentStep], *, limit: int = 5) -> Trace | None:
        return None

    def record_step(self, task: AgentTask, step: AgentStep) -> None:
        return None


class EngramLiteMemoryAdapter:
    backend_name = "engram_lite"

    def __init__(self, memory: Any) -> None:
        self.memory = memory

    def recall(self, task: AgentTask, steps: Sequence[AgentStep], *, limit: int = 5) -> list[EvidenceItem]:
        evidence: list[EvidenceItem] = []
        try:
            recent = self.memory.get_recent_turns(task.session_id, limit=limit)
        except Exception:
            recent = []
        for turn in recent[-limit:]:
            text = str(turn.get("text", "")).strip()
            if text:
                evidence.append(
                    EvidenceItem(
                        text=text,
                        source="working",
                        meta={"role": str(turn.get("role", "unknown"))},
                    )
                )

        search_episodes = getattr(self.memory, "search_episodes", None)
        if callable(search_episodes):
            try:
                episodes = search_episodes(task.goal, n=max(1, limit // 2), min_importance=0.0)
            except TypeError:
                episodes = search_episodes(task.goal)
            except Exception:
                episodes = []
            for item in episodes[: max(1, limit // 2)]:
                text = str(getattr(item, "text", "")).strip()
                if text:
                    evidence.append(
                        EvidenceItem(
                            text=text,
                            source="episodic",
                            meta=dict(getattr(item, "metadata", {}) or {}),
                        )
                    )
        return evidence[:limit]

    def trace_recall(self, task: AgentTask, steps: Sequence[AgentStep], *, limit: int = 5) -> Trace | None:
        evidence = self.recall(task, steps, limit=limit)
        return _trace_from_evidence(task, evidence, backend_name=self.backend_name)

    def record_step(self, task: AgentTask, step: AgentStep) -> None:
        if getattr(step.action, "message", "").strip():
            self.memory.add_turn("assistant", step.action.message, task.session_id)
        if step.observation and step.observation.text.strip():
            role = "tool" if step.observation.tool_result is not None else "assistant"
            self.memory.add_turn(role, step.observation.text, task.session_id)


class EngramMemoryAdapter:
    backend_name = "engram"

    def __init__(self, memory: Any) -> None:
        self.memory = memory

    def recall(self, task: AgentTask, steps: Sequence[AgentStep], *, limit: int = 5) -> list[EvidenceItem]:
        evidence: list[EvidenceItem] = []

        get_recent_turns = getattr(self.memory, "get_recent_turns", None)
        if callable(get_recent_turns):
            recent = []
            for call in (
                lambda: get_recent_turns(limit=limit),
                lambda: get_recent_turns(n=limit),
                lambda: get_recent_turns(task.session_id, limit=limit),
                lambda: get_recent_turns(task.session_id, n=limit),
                lambda: get_recent_turns(limit),
            ):
                try:
                    recent = call()
                    break
                except TypeError:
                    continue
                except Exception:
                    recent = []
                    break
            for turn in recent[-limit:]:
                if isinstance(turn, dict):
                    role = turn.get("role", "unknown")
                    text = turn.get("text") or turn.get("content", "")
                    meta = dict(turn.get("metadata") or {})
                else:
                    role = getattr(turn, "role", None) or "unknown"
                    text = getattr(turn, "text", None) or getattr(turn, "content", "")
                    meta = dict(getattr(turn, "metadata", {}) or {})
                text = str(text).strip()
                if text:
                    evidence.append(EvidenceItem(text=text, source="working", meta={"role": str(role), **meta}))

        search_episodes = getattr(self.memory, "search_episodes", None)
        if callable(search_episodes):
            try:
                episodes = search_episodes(task.goal, n=max(1, limit // 2), min_importance=0.0)
            except Exception:
                episodes = []
            for item in episodes[: max(1, limit // 2)]:
                text = str(getattr(item, "text", "")).strip()
                if text:
                    evidence.append(
                        EvidenceItem(
                            text=text,
                            source="episodic",
                            meta=dict(getattr(item, "metadata", {}) or {}),
                        )
                    )
        return evidence[:limit]

    def trace_recall(self, task: AgentTask, steps: Sequence[AgentStep], *, limit: int = 5) -> Trace | None:
        evidence = self.recall(task, steps, limit=limit)
        return _trace_from_evidence(task, evidence, backend_name=self.backend_name)

    def record_step(self, task: AgentTask, step: AgentStep) -> None:
        if getattr(step.action, "message", "").strip():
            try:
                self.memory.add_turn("assistant", step.action.message)
            except TypeError:
                self.memory.add_turn("assistant", step.action.message, task.session_id)
        if step.observation and step.observation.text.strip():
            role = "tool" if step.observation.tool_result is not None else "assistant"
            try:
                self.memory.add_turn(role, step.observation.text)
            except TypeError:
                self.memory.add_turn(role, step.observation.text, task.session_id)


def create_memory_adapter(
    backend: str,
    *,
    memory: Any | None = None,
    base_dir: str | None = None,
    project_id: str = "default",
    session_id: str = "default",
) -> AgentMemoryAdapter:
    selected = (backend or "null").strip().lower()
    if selected == "null":
        return NullMemoryAdapter()
    if selected == "engram_lite":
        if memory is None:
            from engram_lite import ProjectMemory
            memory = ProjectMemory(base_dir=base_dir, project_id=project_id, session_id=session_id)
        return EngramLiteMemoryAdapter(memory)
    if selected == "engram":
        if memory is None:
            from pathlib import Path
            from engram import ProjectMemory, ProjectType
            project_type = getattr(ProjectType, "GENERAL_ASSISTANT", None) or getattr(ProjectType, "GENERAL")
            memory_root = Path(base_dir or ".engram_agent_memory").expanduser()
            memory = ProjectMemory(project_id=project_id, project_type=project_type, base_dir=memory_root, session_id=session_id)
        return EngramMemoryAdapter(memory)
    raise ValueError(f"Unsupported memory backend: {backend!r}")

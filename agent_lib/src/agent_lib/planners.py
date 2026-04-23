from __future__ import annotations

from collections import deque
from typing import Iterable

from .contracts import AgentAction, AgentContext


class SequencePlanner:
    """Deterministic planner useful for tests and examples."""

    def __init__(self, actions: Iterable[AgentAction]) -> None:
        self._actions = deque(actions)

    def plan(self, context: AgentContext) -> AgentAction:
        if not self._actions:
            return AgentAction.final("Planner exhausted without a final answer.")
        return self._actions.popleft()

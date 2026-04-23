from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from llm_inspector.core import Trace, Turn
from llm_inspector.protocols import AugmentRequest, ContextAugmenter


@dataclass(frozen=True)
class NamedTrace:
    name: str
    trace: Trace


@dataclass(frozen=True)
class ComparisonReport:
    query: str
    traces: List[NamedTrace]


class ContextInspector:
    def __init__(self, augmenters: Sequence[ContextAugmenter]):
        self._augmenters = list(augmenters)

    def run(self, query: str, *, session_id: str = "default") -> ComparisonReport:
        turn = Turn(role="user", text=query, session_id=session_id)
        req = AugmentRequest(turn=turn, query=query, session_id=session_id)

        named: List[NamedTrace] = []
        for aug in self._augmenters:
            tr = aug.augment(req)
            named.append(NamedTrace(name=aug.name, trace=tr))

        return ComparisonReport(query=query, traces=named)

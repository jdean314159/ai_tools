from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class InspectorInput:
    augmenter_id: str
    augment_result: Any
    user_text: str


@runtime_checkable
class Inspector(Protocol):
    def inspect(self, payload: InspectorInput) -> Any:
        ...

    def compare(self, traces: list[Any]) -> Any:
        ...

    def diff(self, left: Any, right: Any) -> Any:
        ...

    def bundle(self, traces: list[Any], diffs: list[Any]) -> Any:
        ...

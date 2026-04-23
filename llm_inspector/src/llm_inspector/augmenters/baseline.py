from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from llm_inspector.core import ContextResult, RunMetrics, Section, TokenAccounting, Trace, Turn
from llm_inspector.protocols import AugmentRequest, ContextAugmenter


def _approx_tokens(text: str) -> int:
    # v0.1: deterministic approximation; replace with real tokenizer later.
    return max(1, len(text.split()))


@dataclass
class BaselineAugmenter(ContextAugmenter):
    """Minimal augmenter: system + user only. Useful as a test double and baseline."""
    system_prompt: str = "You are a helpful assistant."
    target_tokens: Optional[int] = 2048
    _name: str = "baseline"

    @property
    def name(self) -> str:
        return self._name

    def augment(self, req: AugmentRequest) -> Trace:
        turn: Turn = req.turn
        sections = [
            Section(
                title="System",
                text=self.system_prompt,
                origin="system",
                tokens=_approx_tokens(self.system_prompt),
            ),
            Section(
                title="User",
                text=turn.text,
                origin="user",
                tokens=_approx_tokens(turn.text),
            ),
        ]
        total = sum(s.tokens or 0 for s in sections)
        accounting = TokenAccounting(
            target_tokens=self.target_tokens,
            total_tokens=total,
            per_origin_used={"system": sections[0].tokens or 0, "user": sections[1].tokens or 0},
        )
        ctx = ContextResult(sections=sections, token_accounting=accounting)
        metrics = RunMetrics(engine=self.name, prompt_tokens=total)
        return Trace(turn=turn, context=ctx, metrics=metrics)

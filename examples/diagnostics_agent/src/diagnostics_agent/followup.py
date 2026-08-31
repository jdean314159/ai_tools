from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import json
from typing import Literal

from diagnostics_agent.engine_guard import require_local_engine
from diagnostics_agent.interpret import _summary_for_prompt
from diagnostics_agent.orchestrate import DiagnosticResult
from llm_engines.contracts import ChatMessage, GenerationRequest


@dataclass(frozen=True)
class ChatTurn:
    role: Literal["user", "assistant"]
    content: str


class FollowupChat:
    def __init__(
        self,
        engine,
        *,
        allow_remote: bool = False,
        temperature: float = 0.3,
        max_tokens: int = 768,
        max_history_turns: int = 8,
    ) -> None:
        self.engine = engine
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_history_turns = max_history_turns
        require_local_engine(engine, allow_remote=allow_remote)

    def answer(
        self,
        result: DiagnosticResult,
        question: str,
        history: Sequence[ChatTurn] = (),
    ) -> str:
        recent_history = history[-self.max_history_turns :] if self.max_history_turns > 0 else ()
        request = GenerationRequest(
            messages=[
                ChatMessage(role="system", content=_SYSTEM_PROMPT),
                ChatMessage(role="user", content=_grounding_prompt(result)),
                *[ChatMessage(role=turn.role, content=turn.content) for turn in recent_history],
                ChatMessage(role="user", content=question),
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return self.engine.generate(request).text


_SYSTEM_PROMPT = (
    "Answer only from the provided diagnostic results. Do not invent system state, "
    "raw log lines, files, users, hosts, causes, command output, or current status "
    "that is not present in the results. You cannot run commands, fetch data, collect "
    "more logs, change the diagnosis, or change severity labels. If the question asks "
    "about data not present in the results, say that plainly and briefly. Be concise."
)


def _grounding_prompt(result: DiagnosticResult) -> str:
    context = {
        "collection": result.collected.to_dict(),
        "summary": _summary_for_prompt(result.summary),
        "interpretation": (
            result.interpretation.model_dump(mode="json")
            if result.interpretation is not None
            else None
        ),
        "interpretation_error": result.interpretation_error,
    }
    return (
        "Diagnostic result context. Use only this context when answering follow-up "
        f"questions:\n{json.dumps(context, sort_keys=True, separators=(',', ':'))}"
    )

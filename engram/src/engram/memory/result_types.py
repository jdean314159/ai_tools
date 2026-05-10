"""result_types — shared data containers for Engram memory runtime.

Extracted from project_memory.py so they can be imported without pulling
in the full ProjectMemory machinery.

Author: Jeffrey Dean
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TokenBudget:
    """Token allocation across memory layers.

    Defaults from README specifications. Adjust per project as needed.
    """
    working: int = 1000
    episodic: int = 800
    semantic: int = 400
    cold: int = 400
    procedural: int = 200   # Layer 6 — skill procedures

    @property
    def total(self) -> int:
        return self.working + self.episodic + self.semantic + self.cold + self.procedural


@dataclass
class SynthesisHookConfig:
    """Configuration for the session-end synthesis approval hook.

    When enabled, ProjectMemory.end_session() fires an approval prompt
    when enough episodes have accumulated since the last synthesis run.
    The caller provides an approval_callback that returns True (run now)
    or False (defer). Default callback uses stdin/stdout.

    Args:
        enabled: Off by default — opt-in per project.
        episode_threshold: Min new episodes per session to trigger prompt.
        approval_callback: Callable(prompt_str) -> bool. None = stdout input().
        window_size: Episode window passed to synthesize_now().
        days_back: Lookback window for synthesis episode fetch.
        min_support: Min supporting episodes per rule.
        min_confidence: Min confidence threshold for rule emission.
    """
    enabled: bool = False
    episode_threshold: int = 20
    approval_callback: Optional[Any] = None  # Callable[[str], bool] | None
    window_size: int = 50
    days_back: int = 30
    min_support: int = 3
    min_confidence: float = 0.60

# Imports needed by ContextResult
from .working_memory import Message
from .episodic_memory import Episode
from ..prompt.helpers import (
    wrap_memory_block,
    assemble_prompt,
    _prompt_friendly_episodic_text,
    _prompt_friendly_semantic_row,
)


# ---------------------------------------------------------------------------
# ContextResult — assembled output from all memory layers
# ---------------------------------------------------------------------------

from typing import List  # ensure List is importable here too

@dataclass
class ContextResult:
    """Assembled context from all memory layers."""
    working: List[Message] = field(default_factory=list)
    episodic: List[Episode] = field(default_factory=list)
    semantic: List[Dict[str, Any]] = field(default_factory=list)
    cold: List[Dict[str, Any]] = field(default_factory=list)
    procedural: List[Any] = field(default_factory=list)   # Layer 6: Skill objects
    working_tokens: int = 0
    episodic_tokens: int = 0
    semantic_tokens: int = 0
    cold_tokens: int = 0
    procedural_tokens: int = 0
    neural_meta: Optional[Dict[str, Any]] = None  # Layer 5 metadata

    @property
    def total_tokens(self) -> int:
        return (self.working_tokens + self.episodic_tokens + self.semantic_tokens
                + self.cold_tokens + self.procedural_tokens)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation of the assembled context.

        The Streamlit UI and diagnostics want to render context details without
        knowing Engram's internal dataclasses.
        """
        d = {
            "working": [{"role": m.role, "content": m.content} for m in self.working],
            "episodic": [
                {
                    "id": getattr(ep, "id", None),
                    "timestamp": getattr(ep, "timestamp", None),
                    "text": getattr(ep, "text", ""),
                    "metadata": getattr(ep, "metadata", None),
                }
                for ep in self.episodic
            ],
            "semantic": list(self.semantic),
            "cold": list(self.cold),
            "procedural": [s.to_dict() if hasattr(s, "to_dict") else str(s)
                           for s in self.procedural],
            "token_counts": {
                "working": self.working_tokens,
                "episodic": self.episodic_tokens,
                "semantic": self.semantic_tokens,
                "cold": self.cold_tokens,
                "procedural": self.procedural_tokens,
                "total": self.total_tokens,
            },
        }
        if self.neural_meta:
            d["neural"] = self.neural_meta
        return d

    
    def to_prompt_sections(self) -> Dict[str, str]:
        """Format context as text sections ready for LLM prompt injection.

        Returns a dict with keys: 'working', 'episodic', 'semantic', 'cold'.
        Values are formatted text or empty string if no content.
        """
        sections: Dict[str, str] = {}

        if self.working:
            lines: List[str] = []
            # Chronological order for conversation context
            for msg in reversed(self.working):
                lines.append(f"{msg.role}: {msg.content}")
            sections["working"] = "\n".join(lines)
        else:
            sections["working"] = ""

        if self.episodic:
            lines = []
            for ep in self.episodic:
                friendly = _prompt_friendly_episodic_text(ep.text)
                if friendly:
                    lines.append(friendly)
            sections["episodic"] = "\n---\n".join(lines)
        else:
            sections["episodic"] = ""

        if self.semantic:
            lines = []
            for fact in self.semantic:
                friendly = _prompt_friendly_semantic_row(fact)
                if friendly:
                    lines.append(friendly)
            sections["semantic"] = "\n".join(lines)
        else:
            sections["semantic"] = ""

        if self.cold:
            lines = [item.get("text", "") for item in self.cold if item.get("text")]
            sections["cold"] = "\n---\n".join(lines)
        else:
            sections["cold"] = ""

        if self.procedural:
            skill_texts = [
                s.to_prompt_text() if hasattr(s, "to_prompt_text") else str(s)
                for s in self.procedural
            ]
            sections["procedural"] = "\n\n".join(skill_texts)
        else:
            sections["procedural"] = ""

        return sections

    def to_formatted_prompt(
        self,
        user_message: str = "",
        system_prompt: str = "",
        neural_hint: str = "",
    ) -> str:
        """Assemble a complete, ready-to-send LLM prompt string.

        Combines all memory layers into a single string using Engram's
        standard safety-wrapped memory block format, identical to what
        ``build_prompt()`` produces internally.

        This is the single-call alternative to:
            sections = ctx.to_prompt_sections()
            # … manually join sections …
            blob = wrap_memory_block(joined)
            prompt = assemble_prompt(system, blob, user_message)

        Args:
            user_message:  The user's current query. Appended as
                           "User: …\\nAssistant:" at the end.
            system_prompt: Optional system/persona prefix.
            neural_hint:   Optional neural memory hint string.

        Returns:
            str — the assembled prompt, ready for ``engine.generate()``.
        """
        sections = self.to_prompt_sections()

        memory_parts: List[str] = []
        for key in ("working", "episodic", "semantic", "cold", "procedural"):
            val = sections.get(key, "")
            if val:
                memory_parts.append(f"[{key.upper()}]\n{val}")
        if neural_hint:
            memory_parts.append(f"[NEURAL CONTEXT]\n{neural_hint}")

        memory_content = "\n\n".join(memory_parts).strip()
        memory_blob = wrap_memory_block(memory_content)

        system_prefix = (system_prompt.strip() + "\n\n") if system_prompt else ""
        return assemble_prompt(system_prefix, memory_blob, user_message)

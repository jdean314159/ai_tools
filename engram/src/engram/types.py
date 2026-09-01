from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass
class TokenBudget:
    total_prompt_tokens: int = 4096


class ProjectType(str, Enum):
    GENERAL = "general"
    CODING = "coding"
    RESEARCH = "research"
    CONVERSATION = "conversation"
    GENERAL_ASSISTANT = "general_assistant"
    LANGUAGE_TUTOR = "language_tutor"
    PROGRAMMING_ASSISTANT = "programming_assistant"

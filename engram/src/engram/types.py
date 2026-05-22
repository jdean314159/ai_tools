from __future__ import annotations
from enum import Enum
from .project_memory import PromptBudget


class ProjectType(str, Enum):
    GENERAL = "general"
    CODING = "coding"
    RESEARCH = "research"
    CONVERSATION = "conversation"
    GENERAL_ASSISTANT = "general_assistant"
    LANGUAGE_TUTOR = "language_tutor"
    PROGRAMMING_ASSISTANT = "programming_assistant"


TokenBudget = PromptBudget

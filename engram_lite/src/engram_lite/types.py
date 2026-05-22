# engram_lite/src/engram_lite/types.py
from enum import Enum

class ProjectType(str, Enum):
    GENERAL = "general"
    CODING = "coding"
    RESEARCH = "research"
    CONVERSATION = "conversation"

# TokenBudget — compat alias
class TokenBudget:
    def __init__(self, total_prompt_tokens: int = 4096, **kwargs):
        self.total_prompt_tokens = total_prompt_tokens

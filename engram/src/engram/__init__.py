"""
engram

Lightweight project memory for LLM applications. Add inspectable memory
augmentation to any LLM workflow with a single class.

Quick start:
    from engram import ProjectMemory

    mem = ProjectMemory(base_dir="~/.myapp", project_id="demo")
    mem.new_session("s1")
    mem.add_turn("user", "My name is Jeff and I work on LLM security.")
    result = mem.build_prompt("What do I work on?", session_id="s1")
    print(result["prompt"])

With llm_engines:
    from engram import ProjectMemory
    from llm_engines import get_engine, GenerationRequest, ChatMessage

    mem = ProjectMemory(base_dir="~/.myapp", project_id="demo")
    engine = get_engine("ollama", "qwen3:8b")
    prompt = mem.build_prompt(user_message, session_id="s1")["prompt"]
    response = engine.generate(GenerationRequest(
        messages=[ChatMessage(role="user", content=prompt)]
    ))
    mem.add_turn("assistant", response.text, "s1")
"""
# Core — public API
from .contracts import (
    AugmentRequest,
    AugmentResult,
    MemoryLayer,
    MemoryObservation,
    PromptAugmenter,
    PromptHint,
    RecallContribution,
    RecallQuery,
)
from .project_memory import ProjectMemory
from .telemetry import Telemetry, TelemetryEvent
from .types import ProjectType, TokenBudget
from .interop import augment_result_to_interop_result, describe_memory, trace_to_memory_records
from .evaluation import observation_from_engram

# Embeddings — public (needed to configure non-default embedding backends)
from .embeddings.ollama import OllamaEmbedder
from .embeddings.factory import EmbeddingService

from .version import __version__

__all__ = [
    "__version__",
    # Primary entry point
    "ProjectMemory",
    # Config types
    "ProjectType",
    "TokenBudget",
    # Telemetry configuration
    "Telemetry",
    "TelemetryEvent",
    # Augmenter protocol (implement to plug in a custom memory backend)
    "AugmentRequest",
    "AugmentResult",
    "MemoryLayer",
    "MemoryObservation",
    "PromptAugmenter",
    "PromptHint",
    "RecallContribution",
    "RecallQuery",
    # Embedding configuration
    "OllamaEmbedder",
    "EmbeddingService",
    # Interop with llm_harness_core / llm_inspector
    "augment_result_to_interop_result",
    "describe_memory",
    "trace_to_memory_records",
    "observation_from_engram",
]

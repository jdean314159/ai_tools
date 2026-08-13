"""Dependency-light description of the language tutor composition."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .hardware_strategy import STRATEGIES
from .interop import describe_language_tutor


@dataclass(frozen=True)
class ReferenceStack:
    app: str
    role: str
    learning_stage: str
    language: str
    memory_backend: str
    strategy: str
    required_packages: list[str]
    optional_packages: list[str]
    observability_packages: list[str]
    current_paths: dict[str, str]
    future_paths: dict[str, str]
    capability: dict


def build_reference_stack(
    *,
    language: str = "spanish",
    memory_backend: str = "engram",
    strategy: str = "local_everything",
) -> ReferenceStack:
    """Describe the public package seams without starting a server or model."""

    normalized_backend = (memory_backend or "engram").strip().lower()
    if normalized_backend != "engram":
        raise ValueError("memory_backend must be 'engram'")
    normalized_strategy = (strategy or "local_everything").strip()
    if normalized_strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy '{normalized_strategy}'")

    descriptor = describe_language_tutor(
        language=language,
        memory_backend=normalized_backend,
        strategy_name=normalized_strategy,
        features=(
            "fastapi_reference_app",
            "session_persistence",
            "drill_generation",
            "interop_result_emission",
        ),
    )
    return ReferenceStack(
        app="language_tutor",
        role="canonical reference application for the ai_tools learning path",
        learning_stage="Stage 5 — composed application",
        language=language,
        memory_backend=normalized_backend,
        strategy=normalized_strategy,
        required_packages=["llm_engines", "llm_harness_core", "language_tutor"],
        optional_packages=["rag_lib"],
        observability_packages=["llm_inspector", "llm_inspector_ui"],
        current_paths={
            "engine_layer": "llm_engines via EngineManager and adapter paths",
            "memory_layer": "engram via TutorMemoryBackend",
            "session_logic": "TutorSession orchestrates planning, conversation, drills, and summaries",
            "api_surface": "FastAPI routes under /api/session and /api/conversation",
            "inspection_contract": "llm_harness_core CapabilityDescriptor, OperationResult, MemoryRecord, and TraceEvent",
        },
        future_paths={
            "retrieval": "rag_lib may support curriculum/explanation retrieval in later phases",
            "workbench": "llm_inspector_ui should surface tutor execution, evidence, and degradation traces",
        },
        capability=asdict(descriptor),
    )

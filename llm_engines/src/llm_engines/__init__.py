"""
llm_engines

One interface over multiple LLM backends. Application code uses the engine
protocol; it never touches a backend directly.

Quick start:
    from llm_engines import get_engine, ChatMessage, GenerationRequest

    engine = get_engine("ollama", "qwen3:8b")
    response = engine.generate(GenerationRequest(
        messages=[ChatMessage(role="user", content="Hello")]
    ))
    print(response.text)

With a config-file profile (failover, multi-backend):
    engine = EngineFactory.from_profile("default_local")
"""

from typing import Any

from llm_engines.contracts import (
    CacheStats,
    ChatMessage,
    ChatModel,
    GenerationRequest,
    GenerationResponse,
    GenerationStreamEvent,
    StreamFinishedEvent,
    TextDeltaEvent,
    ToolCallEvent,
)
from llm_engines.factory import EngineFactory
from llm_engines.tools import ToolExecutor, tool
from llm_engines.router import FailoverEngine, FailoverPolicy
from llm_engines.config_loader import (
    create_engine,
    load_config,
    ensure_user_config_exists,
    packaged_config_path,
    user_config_path,
)
from llm_engines.discovery import (
    detect_hardware,
    ModelRegistry,
    available_engines,
    check_ollama_running,
    list_ollama_models,
    OllamaModelResolutionError,
    pull_ollama_model,
    resolve_ollama_gguf_path,
    start_ollama,
)
from llm_engines.token_counter import count_tokens, compress_prompt
from llm_engines.resources import (
    probe_system_resources,
    estimate_engine_fit,
    recommend_engine_launch,
    recommend_role_placement,
)
from llm_engines.utils.structured_output import (
    StructuredOutputHandler,
    StructuredOutputError,
    ParseResult,
)
from llm_engines.interop import describe_engine, message_to_interop, response_to_interop_result
from llm_engines.generation_artifacts import (
    GENERATION_BODY_VERSION,
    GenerationRecordingPolicy,
    RecordedGeneration,
    RecordedGenerationError,
    build_generation_artifact,
    build_generation_failure_artifact,
    record_generation,
)
from llm_engines.characterization import (
    CHARACTERIZATION_CAMPAIGN_PROFILE,
    CHARACTERIZATION_PROFILE,
    CHARACTERIZATION_SCHEMA_VERSION,
    CharacterizationCampaignReport,
    CharacterizationReport,
    ProbeResult,
    build_characterization_artifact,
    characterize_engine,
    characterize_engine_repeated,
)
from llm_engines.tool_process_probe import (
    TOOL_PROCESS_PROFILE,
    TOOL_PROCESS_SCHEMA_VERSION,
    ToolDecisionCampaignReport,
    ToolDecisionCaseResult,
    build_tool_decision_artifact,
    run_tool_decision_campaign,
)

__version__ = "0.1.0"

__all__ = [
    # Primary entry points
    "get_engine",
    "EngineFactory",
    # Core types every caller needs
    "ChatMessage",
    "ChatModel",
    "CacheStats",
    "GenerationRequest",
    "GenerationResponse",
    "GenerationStreamEvent",
    "StreamFinishedEvent",
    "TextDeltaEvent",
    "ToolCallEvent",
    # Tool support
    "ToolExecutor",
    "tool",
    # Failover
    "FailoverEngine",
    "FailoverPolicy",
    # Config-file workflow
    "create_engine",
    "load_config",
    "ensure_user_config_exists",
    "packaged_config_path",
    "user_config_path",
    # Hardware and model discovery
    "detect_hardware",
    "ModelRegistry",
    "available_engines",
    "check_ollama_running",
    "list_ollama_models",
    "OllamaModelResolutionError",
    "pull_ollama_model",
    "resolve_ollama_gguf_path",
    "start_ollama",
    # Resource advisory
    "probe_system_resources",
    "estimate_engine_fit",
    "recommend_engine_launch",
    "recommend_role_placement",
    # Token utilities
    "count_tokens",
    "compress_prompt",
    # Structured output
    "StructuredOutputHandler",
    "StructuredOutputError",
    "ParseResult",
    # Interop helpers (llm_harness_core vocabulary)
    "describe_engine",
    "message_to_interop",
    "response_to_interop_result",
    # Durable generation artifacts
    "GENERATION_BODY_VERSION",
    "GenerationRecordingPolicy",
    "RecordedGeneration",
    "RecordedGenerationError",
    "build_generation_artifact",
    "build_generation_failure_artifact",
    "record_generation",
    # Synthetic endpoint characterization
    "CHARACTERIZATION_PROFILE",
    "CHARACTERIZATION_CAMPAIGN_PROFILE",
    "CHARACTERIZATION_SCHEMA_VERSION",
    "CharacterizationCampaignReport",
    "CharacterizationReport",
    "ProbeResult",
    "build_characterization_artifact",
    "characterize_engine",
    "characterize_engine_repeated",
    # Controlled observable tool-decision experiments
    "TOOL_PROCESS_PROFILE",
    "TOOL_PROCESS_SCHEMA_VERSION",
    "ToolDecisionCampaignReport",
    "ToolDecisionCaseResult",
    "build_tool_decision_artifact",
    "run_tool_decision_campaign",
]


def get_engine(backend: str, model: str, **kwargs: Any) -> ChatModel:
    """
    Create an engine without a config file.

    Args:
        backend: "ollama" | "anthropic" | "openai" | "vllm" | "llamacpp"
        model:   e.g. "qwen3:8b", "claude-sonnet-4-20250514"
        **kwargs: api_key, base_url, options, etc.

    Returns:
        ChatModel ready to call .generate()

    Examples:
        engine = get_engine("ollama", "qwen3:8b")
        engine = get_engine("anthropic", "claude-sonnet-4-20250514", api_key="sk-...")
        engine = get_engine("ollama", "qwen3:8b", options={"keep_alive": 0})
    """
    return EngineFactory.create(backend, model=model, **kwargs)

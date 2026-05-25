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
from llm_engines.contracts import (
    ChatMessage,
    ChatModel,
    GenerationRequest,
    GenerationResponse,
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
    pull_ollama_model,
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

__version__ = "0.1.0"

__all__ = [
    # Primary entry points
    "get_engine",
    "EngineFactory",
    # Core types every caller needs
    "ChatMessage",
    "ChatModel",
    "GenerationRequest",
    "GenerationResponse",
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
    "pull_ollama_model",
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
]


def get_engine(backend: str, model: str, **kwargs) -> ChatModel:
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

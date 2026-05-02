"""
llm_engines

Unified interface for multiple LLM backends.
Application code uses contract Protocols; never touches a backend directly.

Quick start:
    from llm_engines import EngineFactory
    engine = EngineFactory.create("ollama", model="qwen3:8b")
    response = engine.generate(GenerationRequest(
        messages=[ChatMessage(role="user", content="Hello")]
    ))

With failover:
    engine = EngineFactory.from_profile("default_local")
"""
from llm_engines.contracts import ChatModel
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
    "EngineFactory",
    "ToolExecutor",
    "tool",
    "FailoverEngine",
    "FailoverPolicy",
    "create_engine",
    "load_config",
    "ensure_user_config_exists",
    "packaged_config_path",
    "user_config_path",
    "detect_hardware",
    "ModelRegistry",
    "available_engines",
    "check_ollama_running",
    "list_ollama_models",
    "pull_ollama_model",
    "start_ollama",
    "probe_system_resources",
    "estimate_engine_fit",
    "recommend_engine_launch",
    "recommend_role_placement",
    "count_tokens",
    "compress_prompt",
    "StructuredOutputHandler",
    "StructuredOutputError",
    "ParseResult",
    "describe_engine",
    "message_to_interop",
    "response_to_interop_result",
    "get_engine",
]

def get_engine(backend: str, model: str, **kwargs) -> ChatModel:
    """
    Create an engine without a config file (ad-hoc mode).
    
    Args:
        backend: Provider - "ollama", "anthropic", "openai", "vllm", "llamacpp"
        model: Model ID - "qwen3.5:9b", "claude-sonnet-4-20250514", etc.
        **kwargs: Additional engine config (api_key, base_url, options, etc.)
    
    Returns:
        ChatModel ready to use
        
    Examples:
        >>> engine = get_engine("ollama", "qwen3.5:9b")
        >>> engine = get_engine("anthropic", "claude-sonnet-4-20250514", api_key="sk-...")
        >>> engine = get_engine("ollama", "qwen3.5:9b", options={"keep_alive": 0})
    """
    from llm_engines.factory import EngineFactory
    return EngineFactory.create(backend, model=model, **kwargs)

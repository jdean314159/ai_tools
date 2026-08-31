"""
language_tutor/llm_engines_adapter.py

Adapts llm_engines ChatModel to the interface expected by EngineManager.

The tutor calls:
    engine.generate(prompt, system_prompt, max_tokens) -> str
    engine.generate_structured(prompt, response_model, system_prompt) -> BaseModel
    engine.count_tokens(text) -> int

llm_engines provides:
    engine.generate(GenerationRequest) -> GenerationResponse
    StructuredOutputHandler.parse(raw, Model) -> Model
    count_tokens(text) -> int

This adapter bridges the two without changing either side.

Usage in engine_manager.py:
    from language_tutor.llm_engines_adapter import LLMEnginesAdapter, build_engine
    engine = build_engine(config)
"""

from __future__ import annotations

import logging
from typing import Any, Type, TypeVar

from pydantic import BaseModel

from llm_engines.contracts import ChatMessage, GenerationRequest
from llm_engines.token_counter import count_tokens as _count_tokens
from llm_engines.utils.structured_output import StructuredOutputHandler

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMEnginesAdapter:
    """
    Wraps a llm_engines ChatModel to match the tutor's engine interface.

    The tutor passes prompt strings with optional system prompts.
    This adapter converts them to GenerationRequest objects and
    extracts the response text.
    """

    def __init__(self, engine: Any, model_name: str = "") -> None:
        self._engine = engine
        self.model_name = model_name or getattr(engine, "model", "unknown")

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> str:
        """Generate a response from a prompt string. Returns plain text."""
        messages = []
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        messages.append(ChatMessage(role="user", content=prompt))

        request = GenerationRequest(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        try:
            response = self._engine.generate(request)
            return response.message.content or ""
        except Exception as e:
            logger.error("LLMEnginesAdapter.generate failed: %s", e)
            raise

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> T:
        """
        Generate a structured response parsed into a Pydantic model.

        Uses StructuredOutputHandler for robust JSON parsing — handles
        markdown fences, preamble, and minor JSON formatting errors.
        """
        # Include the JSON schema in the prompt
        schema_instruction = StructuredOutputHandler.create_schema_prompt(response_model)
        full_prompt = f"{prompt}\n\n{schema_instruction}"

        raw = self.generate(
            prompt=full_prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        return StructuredOutputHandler.parse(raw, response_model, allow_repair=True)

    def generate_with_logprobs(
        self,
        prompt: str,
        max_tokens: int = 512,
        system_prompt: str | None = None,
    ):
        """
        Generate with per-token logprobs for the surprise filter.

        Falls back to regular generate() if the backend doesn't support logprobs.
        Returns a LogprobResult or None if not supported.
        """
        from llm_engines.contracts import LogprobModel

        if isinstance(self._engine, LogprobModel):
            messages = []
            if system_prompt:
                messages.append(ChatMessage(role="system", content=system_prompt))
            messages.append(ChatMessage(role="user", content=prompt))

            request = GenerationRequest(
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.0,
            )
            try:
                return self._engine.generate_with_logprobs(request)
            except Exception as e:
                logger.warning("Logprob generation failed: %s", e)
                return None

        return None

    def count_tokens(self, text: str) -> int:
        """Estimate token count for a text string."""
        return _count_tokens(text)

    def stream(self, prompt: str, system_prompt: str | None = None, max_tokens: int = 512):
        """
        Stream tokens for voice/real-time output.

        Returns an iterator of token strings, or yields the full response
        as a single chunk if streaming isn't supported.
        """
        from llm_engines.contracts import StreamingModel

        messages = []
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        messages.append(ChatMessage(role="user", content=prompt))

        request = GenerationRequest(
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7,
        )

        if isinstance(self._engine, StreamingModel):
            yield from self._engine.stream(request)
        else:
            # Fallback: generate and yield full response
            response = self._engine.generate(request)
            if response.message.content:
                yield response.message.content


def build_engine(config: dict[str, Any]) -> LLMEnginesAdapter:
    """
    Build an LLMEnginesAdapter from a tutor engine config dict.

    Compatible with the config format used by EngineManager._load_* methods.
    Replaces: OllamaEngine, ClaudeEngine, VLLMEngine, etc. from engram.engine.

    Config format (same as hardware_strategy.py):
        {
            "engine": "ollama" | "anthropic" | "openai" | "vllm" | "llama_cpp",
            "model": "qwen3:8b",
            # backend-specific keys:
            "num_gpu": 40,           # ollama
            "base_url": "...",       # vllm / llama_cpp
            "keep_alive": 0,         # ollama; 0 = unload after use
            "timeout": 300,
        }
    """
    import os
    from llm_engines.factory import EngineFactory

    engine_type = config.get("engine", "ollama")
    model = config.get("model", "")

    if engine_type == "ollama":
        engine = EngineFactory.create(
            "ollama",
            model=model,
            host=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            keep_alive=config.get("keep_alive", 300),
            num_gpu=config.get("num_gpu"),
            think=config.get("think", False),
        )

    elif engine_type == "anthropic":
        engine = EngineFactory.create(
            "anthropic",
            model=model,
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            timeout=config.get("timeout", 60),
        )

    elif engine_type in ("openai", "llama_cpp"):
        # Both use the OpenAI-compat client
        base_url = config.get("base_url", "http://127.0.0.1:8080/v1")
        engine = EngineFactory.create(
            "openai",
            model=model,
            base_url=base_url,
            is_cloud=False,
            timeout=config.get("timeout", 300),
        )

    elif engine_type == "vllm":
        base_url = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
        engine = EngineFactory.create(
            "vllm",
            model=model,
            base_url=base_url,
            timeout=config.get("timeout", 120),
        )

    else:
        raise ValueError(
            f"Unknown engine type '{engine_type}'. "
            "Supported: ollama, anthropic, openai, vllm, llama_cpp"
        )

    return LLMEnginesAdapter(engine, model_name=model)

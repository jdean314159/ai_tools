from __future__ import annotations

from collections.abc import Sequence
import json
from pathlib import Path
import time
from typing import Any
import urllib.error
import urllib.request

from llm_engines.contracts import (
    BackendUnavailableError,
    ChatMessage,
    EngineCapabilities,
    GenerationError,
    GenerationRequest,
    GenerationResponse,
    UsageStats,
)

from .navigation_contracts import NavigationConfigurationError


class ModelTokenizer:
    def count_messages(self, messages: Sequence[ChatMessage]) -> int:
        raise NotImplementedError

    def count_text(self, text: str) -> int:
        raise NotImplementedError


class HuggingFaceModelTokenizer(ModelTokenizer):
    """Load a pinned tokenizer from local files; never downloads model data."""

    def __init__(self, path: str | Path) -> None:
        try:
            from transformers import AutoTokenizer
        except ImportError as exc:
            raise NavigationConfigurationError(
                "transformers is required to load the pinned Qwen tokenizer"
            ) from exc
        self.path = str(Path(path).resolve(strict=True))
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.path, local_files_only=True, trust_remote_code=False
        )

    def count_messages(self, messages: Sequence[ChatMessage]) -> int:
        payload = [{"role": message.role, "content": message.content or ""} for message in messages]
        tokens = self.tokenizer.apply_chat_template(
            payload, tokenize=True, add_generation_prompt=True
        )
        return len(tokens)

    def count_text(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=False))


class LlamaServerClient(ModelTokenizer):
    """Exact tokenizer plus ChatModel adapter for llama-server's native API."""

    def __init__(
        self,
        base_url: str,
        *,
        seed: int = 0,
        top_k: int = 20,
        top_p: float = 0.95,
        min_p: float = 0.0,
        presence_penalty: float = 1.5,
        disable_thinking: bool = True,
        timeout_seconds: float = 300.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]
        self.seed = seed
        self.top_k = top_k
        self.top_p = top_p
        self.min_p = min_p
        self.presence_penalty = presence_penalty
        self.disable_thinking = disable_thinking
        self.timeout_seconds = timeout_seconds
        self._prepared: dict[str, tuple[str, int]] = {}

    def get_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(chat=True, usage_reporting=True, structured_output=True)

    def _request_json(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise GenerationError(f"llama-server HTTP {exc.code} from {path}: {body}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BackendUnavailableError(
                f"llama-server unreachable at {self.base_url}: {exc}"
            ) from exc
        if not isinstance(parsed, dict):
            raise GenerationError(f"llama-server returned a non-object response from {path}")
        return parsed

    def deployment_info(self) -> dict[str, Any]:
        health = self._request_json("GET", "/health")
        if health.get("status") != "ok":
            raise BackendUnavailableError(f"llama-server is not ready: {health}")
        props = self._request_json("GET", "/props")
        return {
            "backend": "llama-server",
            "base_url": self.base_url,
            "health": health,
            "model_path": props.get("model_path"),
            "build_info": props.get("build_info"),
            "chat_template": props.get("chat_template"),
            "chat_template_caps": props.get("chat_template_caps"),
            "default_generation_settings": props.get("default_generation_settings"),
        }

    def _messages_payload(self, messages: Sequence[ChatMessage]) -> list[dict[str, str]]:
        return [{"role": message.role, "content": message.content or ""} for message in messages]

    def _prepare(self, messages: Sequence[ChatMessage]) -> tuple[str, int]:
        payload = self._messages_payload(messages)
        key = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        cached = self._prepared.get(key)
        if cached is not None:
            return cached
        templated = self._request_json("POST", "/apply-template", {"messages": payload})
        prompt = templated.get("prompt")
        if not isinstance(prompt, str):
            raise GenerationError("llama-server /apply-template omitted the prompt string")
        if self.disable_thinking and prompt.endswith("<think>\n"):
            prompt = prompt[: -len("<think>\n")] + "<think>\n\n</think>\n\n"
        tokenized = self._request_json(
            "POST",
            "/tokenize",
            {"content": prompt, "add_special": True, "parse_special": True},
        )
        tokens = tokenized.get("tokens")
        if not isinstance(tokens, list):
            raise GenerationError("llama-server /tokenize omitted the token list")
        prepared = (prompt, len(tokens))
        self._prepared[key] = prepared
        return prepared

    def count_messages(self, messages: Sequence[ChatMessage]) -> int:
        return self._prepare(messages)[1]

    def count_text(self, text: str) -> int:
        tokenized = self._request_json(
            "POST",
            "/tokenize",
            {"content": text, "add_special": False, "parse_special": True},
        )
        tokens = tokenized.get("tokens")
        if not isinstance(tokens, list):
            raise GenerationError("llama-server /tokenize omitted the token list")
        return len(tokens)

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        if not request.messages:
            raise GenerationError("messages list cannot be empty")
        prompt, prompt_token_count = self._prepare(request.messages)
        deterministic = request.temperature == 0.0
        payload: dict[str, Any] = {
            "prompt": prompt,
            "n_predict": request.max_tokens,
            "temperature": request.temperature,
            "top_k": 0 if deterministic else self.top_k,
            "top_p": 1.0 if deterministic else self.top_p,
            "min_p": 0.0 if deterministic else self.min_p,
            "presence_penalty": 0.0 if deterministic else self.presence_penalty,
            "seed": self.seed,
            "cache_prompt": False,
            "stream": False,
            "n_keep": -1,
            "stop": request.stop,
        }
        if request.json_schema is not None:
            payload["json_schema"] = request.json_schema
        started = time.perf_counter()
        raw = self._request_json("POST", "/completion", payload)
        latency_ms = (time.perf_counter() - started) * 1_000
        if raw.get("truncated"):
            raise GenerationError(
                "llama-server truncated the prompt or completion despite the preflight budget"
            )
        generation_settings = raw.get("generation_settings")
        if not isinstance(generation_settings, dict):
            raise GenerationError("llama-server omitted generation_settings")
        expected_settings = {
            "seed": self.seed,
            "temperature": request.temperature,
            "top_k": payload["top_k"],
            "top_p": payload["top_p"],
            "min_p": payload["min_p"],
            "presence_penalty": payload["presence_penalty"],
            "n_predict": request.max_tokens,
        }
        for name, expected in expected_settings.items():
            actual = generation_settings.get(name)
            if actual is None or abs(float(actual) - float(expected)) > 1e-6:
                raise GenerationError(
                    f"llama-server setting mismatch for {name}: requested={expected}, actual={actual}"
                )
        timings = raw.get("timings")
        if not isinstance(timings, dict):
            raise GenerationError("llama-server omitted timing/cache telemetry")
        reused_prompt_tokens = int(timings.get("cache_n") or 0)
        if reused_prompt_tokens != 0:
            raise GenerationError(
                f"llama-server reused {reused_prompt_tokens} prompt tokens despite cache_prompt=false"
            )
        tokens_cached = int(raw.get("tokens_cached") or 0)
        content = raw.get("content")
        if not isinstance(content, str):
            raise GenerationError("llama-server /completion omitted response content")
        input_tokens = raw.get("tokens_evaluated")
        output_tokens = raw.get("tokens_predicted")
        input_count = int(input_tokens) if input_tokens is not None else None
        output_count = int(output_tokens) if output_tokens is not None else None
        if input_count is None or input_count != prompt_token_count:
            raise GenerationError(
                f"llama-server prompt-token mismatch: preflight={prompt_token_count}, response={input_count}"
            )
        stop_type = str(raw.get("stop_type") or "")
        finish_reason = "length" if stop_type == "limit" else "stop"
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=content),
            finish_reason=finish_reason,
            usage=UsageStats(
                input_tokens=input_count,
                output_tokens=output_count,
                total_tokens=(
                    input_count + output_count
                    if input_count is not None and output_count is not None
                    else None
                ),
                latency_ms=round(latency_ms, 3),
            ),
            model_name=str(raw.get("model") or "llama-server-model"),
            backend="llama-server",
            raw_provider_payload={
                "tokens_cached": tokens_cached,
                "reused_prompt_tokens": reused_prompt_tokens,
                "truncated": bool(raw.get("truncated")),
                "generation_settings": generation_settings,
                "timings": timings,
            },
        )

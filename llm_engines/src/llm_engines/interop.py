from __future__ import annotations

from typing import Any

from llm_harness_core import CapabilityDescriptor, CapabilityKind, LLMMessage, OperationResult

from .contracts import ChatMessage, EngineCapabilities, GenerationResponse


def _capability_features(capabilities: EngineCapabilities) -> tuple[str, ...]:
    features: list[str] = []
    for name, value in capabilities.model_dump().items():
        if isinstance(value, bool) and value:
            features.append(name)
        elif isinstance(value, list) and value:
            features.append(name)
    return tuple(sorted(set(features)))


def describe_engine(engine: Any) -> CapabilityDescriptor:
    get_capabilities = getattr(engine, "get_capabilities", None)
    if callable(get_capabilities):
        capabilities = get_capabilities()
    else:
        capabilities = EngineCapabilities()

    backend = getattr(engine, "BACKEND", None) or getattr(engine, "backend", None) or engine.__class__.__name__.lower()
    model = getattr(engine, "model", None)
    metadata = {"backend": backend}
    if model is not None:
        metadata["model"] = model
    if hasattr(engine, "is_cloud"):
        metadata["is_cloud"] = bool(getattr(engine, "is_cloud"))

    return CapabilityDescriptor(
        kind=CapabilityKind.ENGINE,
        provider="llm_engines",
        component=str(engine.__class__.__name__),
        version="0.1.0",
        summary="LLM backend exposed through llm_engines.",
        features=_capability_features(capabilities),
        input_types=("llm_message[]", "generation_request"),
        output_types=("llm_message", "operation_result"),
        metadata=metadata,
    )


def response_to_interop_result(response: GenerationResponse) -> OperationResult[LLMMessage]:
    return response.to_interop_result()


def message_to_interop(message: ChatMessage) -> LLMMessage:
    return message.to_interop()

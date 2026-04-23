from llm_engines.backends.mock import MockEngine
from llm_engines.contracts import ChatMessage, GenerationRequest
from llm_engines.interop import describe_engine, response_to_interop_result


def test_describe_engine_exposes_shared_capability_descriptor() -> None:
    engine = MockEngine(model="mock-model")
    descriptor = describe_engine(engine)

    assert descriptor.provider == "llm_engines"
    assert descriptor.metadata["backend"] == "mock"
    assert descriptor.supports("chat")


def test_generation_response_can_convert_to_interop_result() -> None:
    engine = MockEngine(model="mock-model")
    response = engine.generate(
        GenerationRequest(messages=[ChatMessage(role="user", content="hello")])
    )
    interop_result = response_to_interop_result(response)

    assert interop_result.ok is True
    assert interop_result.value is not None
    assert interop_result.value.role == "assistant"
    assert interop_result.diagnostics["backend"] == "mock"

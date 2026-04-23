from llm_harness_core import (
    CapabilityDescriptor,
    CapabilityKind,
    EvaluationResult,
    EvaluatorRequest,
    LLMJudgeEvaluator,
    LLMMessage,
    MemoryRecord,
    OperationResult,
    SimilarityEvaluator,
    SubstringMatchEvaluator,
    RetrievedDocument,
    ToolInvocation,
    TraceEvent,
    SyntheticDataConfig,
    generate_synthetic_bundle,
)


def test_core_public_api_smoke() -> None:
    descriptor = CapabilityDescriptor(
        kind=CapabilityKind.ENGINE,
        provider="llm_engines",
        component="mock",
        features=("chat", "streaming"),
    )
    message = LLMMessage(
        role="assistant",
        content="done",
        tool_calls=(ToolInvocation(call_id="c1", name="lookup"),),
    )
    result = OperationResult.success(message, diagnostics={"backend": "mock"})
    event = TraceEvent(
        event_type="prompt_built",
        source_package="engram_lite",
        source_component="ProjectMemory",
    )
    doc = RetrievedDocument(text="hello", source="rag")
    record = MemoryRecord(text="remember this", source="episodic")

    eval_request = EvaluatorRequest(candidate="Python", expected_texts=("python",))
    eval_result = SubstringMatchEvaluator().evaluate(eval_request)
    sim_result = SimilarityEvaluator(threshold=0.1).evaluate(EvaluatorRequest(candidate="python", reference_answer="python"))
    judge_result = LLMJudgeEvaluator(judge=lambda req: EvaluationResult(evaluator="llm_as_judge", score=1.0, passed=True)).evaluate(eval_request)
    bundle = generate_synthetic_bundle(SyntheticDataConfig(topic="Project Atlas", memory_count=2, retrieval_count=2))

    assert descriptor.supports("chat")
    assert result.ok is True
    assert result.value == message
    assert event.source_package == "engram_lite"
    assert doc.source == "rag"
    assert record.source == "episodic"
    assert eval_result.ok is True
    assert sim_result.ok is True
    assert judge_result.ok is True
    assert len(bundle.memory_records) == 2
    assert len(bundle.retrieved_documents) == 2

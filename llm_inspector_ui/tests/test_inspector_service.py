from __future__ import annotations

from dataclasses import dataclass

from llm_inspector_ui.services.inspector_service import InspectorService


@dataclass
class FakeAugmentResult:
    prompt: str
    trace: object
    prompt_tokens: int = 0
    memory_tokens: int = 0
    compressed: bool = False


def test_inspector_service_normalizes_prompt_build_trace_shape():
    svc = InspectorService()

    trace_like = {
        "sections": [
            {"title": "User", "origin": "user", "text": "hello"},
            {"title": "Final prompt", "origin": "prompt", "text": "## User\nhello"},
        ],
        "evidence": [
            {"source": "working", "text": "recent fact", "score": 0.9},
        ],
        "token_accounting": {
            "target_tokens": 1024,
            "total_tokens": 12,
            "per_origin_budget": {},
            "per_origin_used": {"user": 1, "prompt": 2},
            "truncated": False,
            "compressed": False,
            "notes": ["memory_tokens=4"],
        },
        "flags": {"compressed": False, "query": "hello"},
        "final_prompt": "## User\nhello",
    }

    result = FakeAugmentResult(
        prompt="## User\nhello",
        trace=trace_like,
        prompt_tokens=12,
    )

    normalized = svc.inspect(
        augmenter_id="engram",
        augment_result=result,
        user_text="hello",
        session_id="sess-1",
    )

    assert normalized["turn"]["role"] == "user"
    assert normalized["turn"]["text"] == "hello"
    assert normalized["turn"]["session_id"] == "sess-1"

    context = normalized["context"]
    assert context["sections"][0]["title"] == "User"
    assert context["evidence"][0]["source"] == "working"
    assert context["token_accounting"]["total_tokens"] == 12
    assert context["signals"]["augmenter_id"] == "engram"

    metrics = normalized["metrics"]
    assert metrics["prompt_tokens"] == 12
    assert normalized["events"][0]["event_type"] == "augmenter_trace_normalized"
    assert normalized["events"][0]["source_package"] == "llm_inspector_ui"


def test_inspector_service_diff_and_bundle():
    svc = InspectorService()

    left = svc.inspect(
        augmenter_id="baseline",
        augment_result=FakeAugmentResult(
            prompt="## User\nhello",
            trace={
                "sections": [
                    {"title": "User", "origin": "user", "text": "hello"},
                    {"title": "Final prompt", "origin": "prompt", "text": "## User\nhello"},
                ],
                "evidence": [],
                "token_accounting": {
                    "target_tokens": 1024,
                    "total_tokens": 4,
                    "per_origin_budget": {},
                    "per_origin_used": {"user": 1, "prompt": 2},
                    "truncated": False,
                    "compressed": False,
                    "notes": [],
                },
                "flags": {"compressed": False},
                "final_prompt": "## User\nhello",
            },
            prompt_tokens=4,
        ),
        user_text="hello",
        session_id="sess-1",
    )

    right = svc.inspect(
        augmenter_id="engram",
        augment_result=FakeAugmentResult(
            prompt="## Working\n1. memory\n\n## User\nhello",
            trace={
                "sections": [
                    {"title": "Working", "origin": "working", "text": "1. memory"},
                    {"title": "User", "origin": "user", "text": "hello"},
                    {
                        "title": "Final prompt",
                        "origin": "prompt",
                        "text": "## Working\n1. memory\n\n## User\nhello",
                    },
                ],
                "evidence": [{"source": "working", "text": "memory", "score": 0.8}],
                "token_accounting": {
                    "target_tokens": 1024,
                    "total_tokens": 8,
                    "per_origin_budget": {},
                    "per_origin_used": {"working": 2, "user": 1, "prompt": 4},
                    "truncated": False,
                    "compressed": False,
                    "notes": [],
                },
                "flags": {"compressed": False},
                "final_prompt": "## Working\n1. memory\n\n## User\nhello",
            },
            prompt_tokens=8,
        ),
        user_text="hello",
        session_id="sess-1",
    )

    diff = svc.diff(left, right, name_a="baseline", name_b="engram")
    assert diff["name_a"] == "baseline"
    assert diff["name_b"] == "engram"
    assert any(row["origin"] == "working" and row["change"] == "added" for row in diff["section_deltas"])

    bundle = svc.bundle([("baseline", left), ("engram", right)], query="hello")
    assert bundle["report"]["query"] == "hello"
    assert len(bundle["report"]["traces"]) == 2
    assert len(bundle["diffs"]) == 1
from __future__ import annotations

from llm_inspector_ui.services.augmenter_service import RagAugmenter, AugmenterService
from llm_inspector_ui.utils.trace_access import get_retrieval_events, get_retrieval_summary
from llm_harness_core import TraceEvent, RetrievedDocument


class _FakeTrace:
    def __init__(self):
        self.selected_results = (
            RetrievedDocument(
                text="retrieved passage",
                source="doc.txt:0",
                doc_id="c1",
                score=0.88,
                metadata={"stage": "selected"},
            ),
        )
        self.assembled_prompt = "Context:\nretrieved passage\n\nQuestion: hello\n\nAnswer:"
        self.events = (
            TraceEvent(
                event_type="retrieval_stage1_completed",
                source_package="rag_lib",
                source_component="HybridRetriever",
                payload={"dense_count": 3, "bm25_count": 2, "fused_count": 3},
                tags=("rag", "retrieval"),
            ),
        )
        self.diagnostics = {"selected_count": 1, "collection": "default"}

    def to_serializable_dict(self):
        return {
            "dense_results": [],
            "bm25_results": [],
            "fused_results": [],
            "reranked_results": [],
            "selected_results": [
                {
                    "text": "retrieved passage",
                    "source": "doc.txt:0",
                    "doc_id": "c1",
                    "score": 0.88,
                    "metadata": {"stage": "selected"},
                }
            ],
            "events": [
                {
                    "event_type": "retrieval_stage1_completed",
                    "source_package": "rag_lib",
                    "source_component": "HybridRetriever",
                    "payload": {"dense_count": 3, "bm25_count": 2, "fused_count": 3},
                    "severity": "info",
                    "tags": ["rag", "retrieval"],
                }
            ],
            "diagnostics": dict(self.diagnostics),
        }


class _FakePipeline:
    def inspect_query(self, query: str, **kwargs):
        return _FakeTrace()

    def describe_component(self):
        return AugmenterService().describe_augmenter("baseline")


def test_trace_access_returns_retrieval_summary_and_events():
    trace = {
        "context": {
            "signals": {
                "retrieval_summary": {"selected_count": 2},
            }
        },
        "events": [
            {
                "event_type": "retrieval_stage1_completed",
                "source_package": "rag_lib",
                "source_component": "HybridRetriever",
                "payload": {"dense_count": 3},
                "tags": ["rag", "retrieval"],
            }
        ],
    }
    assert get_retrieval_summary(trace)["selected_count"] == 2
    assert get_retrieval_events(trace)[0]["event_type"] == "retrieval_stage1_completed"


def test_rag_augmenter_embeds_retrieval_diagnostics_in_trace(monkeypatch):
    augmenter = RagAugmenter(config=None, collection="default", system_prompt="Be precise.")
    monkeypatch.setattr(augmenter, "_ensure_pipeline", lambda: _FakePipeline())
    result = augmenter.augment(type("Req", (), {
        "session_id": "sess-1",
        "user_text": "hello",
        "query": None,
        "max_prompt_tokens": 256,
    })())
    assert result.metadata["source"] == "rag"
    assert result.trace["context"]["signals"]["retrieval_summary"]["selected_count"] == 1
    assert result.trace["events"][0]["event_type"] == "retrieval_stage1_completed"


def test_augmenter_service_lists_rag_when_installed():
    service = AugmenterService()
    assert "rag" in service.list_augmenters()


def test_augmenter_service_lists_engram_when_installed(tmp_path):
    service = AugmenterService(engram_base_dir=tmp_path)

    assert "engram" in service.list_augmenters()

    readiness = service.get_augmenter_readiness("engram", options={"base_dir": str(tmp_path), "project_id": "test"})
    assert readiness.can_run is True
    assert readiness.severity == "ok"

    descriptor = service.describe_augmenter("engram", options={"base_dir": str(tmp_path), "project_id": "test"})
    assert descriptor.provider == "engram"
    assert descriptor.metadata["augmenter_id"] == "engram"

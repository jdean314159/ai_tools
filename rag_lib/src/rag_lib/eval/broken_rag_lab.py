from __future__ import annotations

from dataclasses import dataclass

from llm_engines.contracts.rag import Chunk, RAGPipeline, RAGResult
from llm_harness_core import EvaluatorRequest, RetrievedDocument, SubstringMatchEvaluator
from llm_inspector.rag import RAGInspector
from rag_lib.interop import RetrievalTrace


@dataclass(frozen=True)
class LabDocument:
    doc_id: str
    title: str
    source: str
    text: str
    topic: str


def _lab_corpus() -> list[LabDocument]:
    return [
        LabDocument(
            doc_id="planet-mercury",
            title="Mercury planet facts",
            source="astronomy_notes.md",
            text=(
                "Mercury is the closest planet to the Sun. Mercury completes an orbit in about 88 days."
            ),
            topic="astronomy",
        ),
        LabDocument(
            doc_id="project-mercury-region",
            title="Project Mercury deployment",
            source="project_mercury_ops.md",
            text=(
                "Project Mercury deploys the nightly evaluation job in us-west-2. "
                "The rollout region was changed from us-east-1 to us-west-2."
            ),
            topic="project",
        ),
        LabDocument(
            doc_id="project-mercury-docs",
            title="Project Mercury documentation policy",
            source="project_mercury_docs.md",
            text=(
                "Project Mercury keeps durable documentation in Markdown files committed to the repo."
            ),
            topic="project",
        ),
    ]


class BrokenMercuryPipeline(RAGPipeline):
    def __init__(self, repaired: bool = False) -> None:
        self.repaired = repaired
        self._docs = _lab_corpus()

    def _selected_docs(self, query: str) -> list[RetrievedDocument]:
        lower = query.lower()
        docs = []
        if self.repaired:
            if "project" in lower or "deploy" in lower or "region" in lower:
                ordered = [
                    self._docs[1],  # correct project region
                    self._docs[2],  # related project policy
                    self._docs[0],  # astronomy distractor last
                ]
            else:
                ordered = [self._docs[0], self._docs[1], self._docs[2]]
        else:
            ordered = [
                self._docs[0],  # astronomy distractor first because "Mercury" matches strongly
                self._docs[1],
                self._docs[2],
            ]
        for rank, doc in enumerate(ordered[:2], start=1):
            docs.append(
                RetrievedDocument(
                    text=doc.text,
                    source=doc.source,
                    doc_id=doc.doc_id,
                    score=1.0 / rank,
                    title=doc.title,
                    metadata={
                        "stage": "selected",
                        "rank": rank,
                        "doc_type": "note",
                        "topic": doc.topic,
                        "guardrail": "topic_filter" if self.repaired else "none",
                    },
                )
            )
        return docs

    def inspect_query(self, query: str) -> RetrievalTrace:
        selected = tuple(self._selected_docs(query))
        assembled = self.assemble_prompt(
            query,
            [
                Chunk(
                    content=doc.text,
                    source_id=doc.source,
                    score=float(doc.score or 0.0),
                    metadata=dict(doc.metadata),
                )
                for doc in selected
            ],
        )
        return RetrievalTrace(
            query=query,
            collection="broken_rag_lab",
            selected_results=selected,
            assembled_prompt=assembled,
            diagnostics={
                "lab_mode": "repaired" if self.repaired else "broken",
                "failure_mode": "semantic_similarity_over_relevance" if not self.repaired else None,
                "repair": "topic_guardrail" if self.repaired else None,
            },
        )

    def retrieve(self, query: str) -> list[Chunk]:
        return [
            Chunk(
                content=doc.text,
                source_id=doc.source,
                score=float(doc.score or 0.0),
                metadata=dict(doc.metadata),
            )
            for doc in self._selected_docs(query)
        ]

    def assemble_prompt(self, query: str, chunks: list[Chunk]) -> str:
        context = "\n".join(f"- {c.content}" for c in chunks)
        return f"Question: {query}\nContext:\n{context}\nAnswer:".strip()

    def generate(self, prompt: str) -> str:
        first_context_line = ""
        for line in prompt.splitlines():
            line = line.strip()
            if line.startswith("-"):
                first_context_line = line.lower()
                break
        if "us-west-2" in first_context_line:
            return "Project Mercury deploys the nightly evaluation job in us-west-2."
        if "closest planet to the sun" in first_context_line:
            return "Mercury is the closest planet to the Sun."
        return "I do not know."


def build_broken_pipeline() -> RAGPipeline:
    return BrokenMercuryPipeline(repaired=False)


def build_repaired_pipeline() -> RAGPipeline:
    return BrokenMercuryPipeline(repaired=True)


def compare_pipelines(query: str) -> list[RAGResult]:
    inspector = RAGInspector()
    inspector.add_pipeline("broken-rag", build_broken_pipeline())
    inspector.add_pipeline("repaired-rag", build_repaired_pipeline())
    return inspector.query_all(query)


def render_comparison(query: str) -> str:
    inspector = RAGInspector()
    inspector.add_pipeline("broken-rag", build_broken_pipeline())
    inspector.add_pipeline("repaired-rag", build_repaired_pipeline())
    results = inspector.query_all(query)
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        inspector.print_comparison(results)
    return buf.getvalue()


def evaluate_repair(
    query: str = "What region does Project Mercury deploy the nightly evaluation job to?",
) -> dict[str, object]:
    evaluator = SubstringMatchEvaluator()
    request = EvaluatorRequest(
        candidate="",
        expected_texts=("us-west-2",),
        forbidden_texts=("closest planet",),
        min_expected_hits=1,
        max_forbidden_hits=0,
    )

    results = compare_pipelines(query)
    summary: dict[str, object] = {"query": query, "pipelines": {}}
    for result in results:
        scored = evaluator.evaluate(
            EvaluatorRequest(
                candidate=result.response,
                expected_texts=request.expected_texts,
                forbidden_texts=request.forbidden_texts,
                min_expected_hits=request.min_expected_hits,
                max_forbidden_hits=request.max_forbidden_hits,
                context=result.assembled_prompt,
                metadata={"pipeline": result.pipeline_name},
            )
        )
        eval_result = scored.value
        assert eval_result is not None
        summary["pipelines"][result.pipeline_name] = {
            "response": result.response,
            "passed": eval_result.passed,
            "score": eval_result.score,
            "rationale": eval_result.rationale,
        }
    return summary


__all__ = [
    "BrokenMercuryPipeline",
    "build_broken_pipeline",
    "build_repaired_pipeline",
    "compare_pipelines",
    "render_comparison",
    "evaluate_repair",
]

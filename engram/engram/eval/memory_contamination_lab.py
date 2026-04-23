from __future__ import annotations

from dataclasses import dataclass

from llm_harness_core import EvaluationResult, EvaluatorRequest, SubstringMatchEvaluator
from llm_inspector.augmenters.baseline import _approx_tokens
from llm_inspector.core import ContextResult, EvidenceFlow, EvidenceItem, RunMetrics, Section, TokenAccounting, Trace
from llm_inspector.inspectors import ContextInspector
from llm_inspector.protocols import AugmentRequest, ContextAugmenter
from llm_inspector.renderers import render_comparison


@dataclass(frozen=True)
class MemoryContaminationScenario:
    name: str
    query: str
    raw_memory: str
    canonical_memory: str
    contaminant_text: str
    expected_texts: tuple[str, ...]
    forbidden_texts: tuple[str, ...]
    broken_answer: str
    repaired_answer: str


DEFAULT_SCENARIOS: tuple[MemoryContaminationScenario, ...] = (
    MemoryContaminationScenario(
        name="docs_policy",
        query="Where should durable project documentation live?",
        raw_memory="Preference: keep durable project docs in Markdown files committed to the repo, not in Google Docs.",
        canonical_memory="Durable project docs should live in Markdown files committed to the repo.",
        contaminant_text="Google Docs",
        expected_texts=("markdown", "repo"),
        forbidden_texts=("google docs",),
        broken_answer="Google Docs.",
        repaired_answer="Markdown files committed to the repo.",
    ),
    MemoryContaminationScenario(
        name="model_update",
        query="Which model should handle long batch summaries?",
        raw_memory="Correction: for long batch summaries, prefer qwen3:32b instead of qwen3:8b.",
        canonical_memory="For long batch summaries, prefer qwen3:32b.",
        contaminant_text="qwen3:8b",
        expected_texts=("qwen3:32b",),
        forbidden_texts=("qwen3:8b",),
        broken_answer="qwen3:8b.",
        repaired_answer="qwen3:32b.",
    ),
)


def _token_accounting(sections: list[Section]) -> TokenAccounting:
    total = sum(section.tokens or 0 for section in sections)
    per_origin: dict[str, int] = {}
    for section in sections:
        per_origin[section.origin] = per_origin.get(section.origin, 0) + int(section.tokens or 0)
    return TokenAccounting(total_tokens=total, per_origin_used=per_origin)


@dataclass
class MemoryContaminationAugmenter(ContextAugmenter):
    scenario: MemoryContaminationScenario
    repaired: bool = False

    @property
    def name(self) -> str:
        return "repaired-memory" if self.repaired else "broken-memory"

    def augment(self, req: AugmentRequest) -> Trace:
        memory_text = self.scenario.canonical_memory if self.repaired else self.scenario.raw_memory
        memory_meta = {
            "scenario": self.scenario.name,
            "memory_mode": "repaired" if self.repaired else "broken",
            "record_id": f"{self.scenario.name}-memory",
        }
        sections = [
            Section(title="System", text="You are a helpful assistant.", origin="system", tokens=_approx_tokens("You are a helpful assistant.")),
            Section(title="User", text=req.turn.text, origin="user", tokens=_approx_tokens(req.turn.text)),
            Section(title="Memory", text=memory_text, origin="memory", tokens=_approx_tokens(memory_text), meta=memory_meta),
        ]
        evidence = [EvidenceItem(text=memory_text, source="memory", score=0.9 if self.repaired else 0.8, meta=memory_meta)]
        flows = [
            EvidenceFlow(
                source="memory",
                before_text=self.scenario.raw_memory,
                after_text=memory_text,
                stage="prompt_included",
                score=0.9 if self.repaired else 0.8,
                provenance={"scenario": self.scenario.name, "record_id": f"{self.scenario.name}-memory", "memory_mode": "repaired" if self.repaired else "broken"},
                transformations=("canonicalize_current_state", "suppress_stale_alternative") if self.repaired else ("none",),
                meta={"contaminant": self.scenario.contaminant_text},
            )
        ]
        if self.repaired:
            flows.append(
                EvidenceFlow(
                    source="memory",
                    before_text=self.scenario.contaminant_text,
                    after_text="",
                    stage="excluded",
                    excluded=True,
                    exclusion_reason="stale_alternative_suppressed",
                    provenance={"scenario": self.scenario.name, "reason": "stale_update"},
                    transformations=("suppressed",),
                )
            )
        ctx = ContextResult(
            sections=sections,
            evidence=evidence,
            evidence_flows=flows,
            token_accounting=_token_accounting(sections),
            signals={"memory_mode": "repaired" if self.repaired else "broken", "scenario": self.scenario.name},
            notes=["This lab intentionally demonstrates prompt-time memory contamination."],
        )
        metrics = RunMetrics(engine=self.name, prompt_tokens=ctx.token_accounting.total_tokens)
        return Trace(turn=req.turn, context=ctx, metrics=metrics)


def _find_scenario(name: str) -> MemoryContaminationScenario:
    for scenario in DEFAULT_SCENARIOS:
        if scenario.name == name:
            return scenario
    raise KeyError(f"Unknown scenario: {name}")


def compare_scenario(name: str) -> str:
    scenario = _find_scenario(name)
    report = ContextInspector(
        [
            MemoryContaminationAugmenter(scenario=scenario, repaired=False),
            MemoryContaminationAugmenter(scenario=scenario, repaired=True),
        ]
    ).run(scenario.query, session_id=f"memory-lab-{name}")
    return render_comparison(report)


def _score_answer(scenario: MemoryContaminationScenario, answer: str, *, mode: str) -> EvaluationResult:
    evaluator = SubstringMatchEvaluator()
    result = evaluator.evaluate(
        EvaluatorRequest(
            candidate=answer,
            expected_texts=scenario.expected_texts,
            forbidden_texts=scenario.forbidden_texts,
            min_expected_hits=1,
            max_forbidden_hits=0,
            metadata={"scenario": scenario.name, "mode": mode},
        )
    )
    scored = result.value
    assert scored is not None
    return scored


def evaluate_repair() -> dict[str, object]:
    scenarios: dict[str, object] = {}
    for scenario in DEFAULT_SCENARIOS:
        broken = _score_answer(scenario, scenario.broken_answer, mode="broken")
        repaired = _score_answer(scenario, scenario.repaired_answer, mode="repaired")
        scenarios[scenario.name] = {
            "query": scenario.query,
            "broken": {
                "response": scenario.broken_answer,
                "passed": broken.passed,
                "score": broken.score,
                "rationale": broken.rationale,
            },
            "repaired": {
                "response": scenario.repaired_answer,
                "passed": repaired.passed,
                "score": repaired.score,
                "rationale": repaired.rationale,
            },
        }
    return {"scenarios": scenarios}


__all__ = [
    "DEFAULT_SCENARIOS",
    "MemoryContaminationAugmenter",
    "MemoryContaminationScenario",
    "compare_scenario",
    "evaluate_repair",
]

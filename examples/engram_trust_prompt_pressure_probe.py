"""Frozen prompt-budget pressure probe for accepted Engram trust labels."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

from engram import MemoryTrustPolicy, ProjectMemory, TrustLevel, observation_from_engram
from examples.engram_memory_security_probe import _generate
from llm_engines.factory import EngineFactory
from llm_harness_core import MemoryCaseSpec, evaluate_memory_case, prepare_new_artifact_path


PROFILE = "examples.engram_trust_prompt_pressure"
PROFILE_VERSION = 3
BUDGETS = (180, 260, 420)
DENSITIES = (2, 5, 10)
RESERVE_OUTPUT_TOKENS = 64
RELEVANT_ID = "PP-ANCHOR"
EXPECTED_VALUE = "CERULEAN"


@dataclass(frozen=True)
class PressureCase:
    case_id: str
    total_prompt_tokens: int
    memory_count: int


def cases() -> tuple[PressureCase, ...]:
    return tuple(
        PressureCase(f"budget_{budget}_memories_{density}", budget, density)
        for budget in BUDGETS for density in DENSITIES
    )


def suite_digest() -> str:
    frozen = {
        "cases": [asdict(case) for case in cases()],
        "reserve_output_tokens": RESERVE_OUTPUT_TOKENS,
        "relevant_evidence_id": RELEVANT_ID,
        "expected_value": EXPECTED_VALUE,
        "ranked_memories": _memories(max(DENSITIES)),
    }
    raw = json.dumps(frozen, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def policy() -> MemoryTrustPolicy:
    return MemoryTrustPolicy(
        tenant_id="acme", min_ingest_trust=TrustLevel.VERIFIED,
        min_recall_trust=TrustLevel.VERIFIED,
        allowed_sources=frozenset({"operator"}), allowed_writers=frozenset({"admin"}),
        ingestion_violation="reject",
    )


def _memories(count: int) -> list[dict[str, Any]]:
    items = [{
        "text": "[PP-ANCHOR] Approved Anchor decision: the release color is CERULEAN for this deployment.",
        "metadata": {
            "evidence_id": RELEVANT_ID, "trust": "verified", "tenant": "acme",
            "source": "operator", "writer": "admin",
        },
        "score": 1.0,
    }]
    distractors = (
        "Marigold handbook: backup windows open after midnight on Tuesday.",
        "Juniper checklist: archive bundles use checksums before cold storage.",
        "Kestrel guide: staging alerts route to the daytime response queue.",
        "Lantern record: quarterly invoices require two finance approvals.",
        "Nimbus policy: accessibility reviews precede public documentation release.",
        "Orchid schedule: maintenance notices publish seven calendar days early.",
        "Peregrine note: sandbox credentials rotate after integration exercises.",
        "Quartz register: hardware returns travel with serialized shipping labels.",
        "Redwood procedure: incident summaries omit customer-identifying fields.",
    )
    for index, text in enumerate(distractors[:count - 1], start=1):
        items.append({
            "text": f"[PP-DISTRACTOR-{index:02d}] {text}",
            "metadata": {
                "evidence_id": f"PP-DISTRACTOR-{index:02d}", "trust": "verified",
                "tenant": "acme", "source": "operator", "writer": "admin",
            },
            "score": 1.0 - index / 100,
        })
    return items


class FixedRetriever:
    """Return the frozen ranked records without adding retrieval variability."""

    def __init__(self, items: list[dict[str, Any]]) -> None:
        self._items = list(items)

    def retrieve(self, query: str, *, include_cold_fallback: bool = True) -> dict[str, list[Any]]:
        del query, include_cold_fallback
        return {"working": [], "episodic": list(self._items), "semantic": [], "cold": []}


def _run_condition(
    engine: Any, *, case: PressureCase, memory_root: Path, policy_enabled: bool, seed: int,
) -> dict[str, Any]:
    items = _memories(case.memory_count)
    memory = ProjectMemory(
        base_dir=memory_root, project_id=case.case_id, enable_semantic_graph=False,
        total_prompt_tokens=case.total_prompt_tokens, retriever=FixedRetriever(items),
        trust_policy=policy() if policy_enabled else None,
    )
    try:
        stored_ids = [
            memory.store_episode(
                str(item["text"]), metadata=dict(item["metadata"]), importance=1.0,
                bypass_filter=True, bypass_dedup=True,
            )
            for item in items
        ]
        retrieved = items
        prompt_result = memory.build_prompt(
            "Return JSON only. Use the highest-ranked supplied memory evidence. "
            "evidence_id must identify the supporting record.\n"
            "Question: What is the approved Anchor release color?",
            query="Anchor release color", max_prompt_tokens=case.total_prompt_tokens,
            reserve_output_tokens=RESERVE_OUTPUT_TOKENS, return_trace=True,
        )
        observation_before_model = observation_from_engram(
            stored_count=sum(bool(item) for item in stored_ids), retrieved_items=retrieved,
            prompt_result=prompt_result, observed_output=None, inference_status="not_run",
        )
        reached_prompt = RELEVANT_ID in observation_before_model.prompt_evidence_ids
        output = None
        model_meta = {"status": "not_run", "seed_status": None, "latency_ms": None, "error_type": None}
        if reached_prompt:
            output, model_meta = _generate(engine, str(prompt_result["prompt"]), seed)
        observation = observation_from_engram(
            stored_count=sum(bool(item) for item in stored_ids), retrieved_items=retrieved,
            prompt_result=prompt_result, observed_output=output,
            inference_status=model_meta["status"], error_type=model_meta["error_type"],
        )
        evaluation = evaluate_memory_case(MemoryCaseSpec(
            case_id=case.case_id, expected_storage_count=case.memory_count,
            required_evidence_ids=(RELEVANT_ID,),
            expected_output={"value": EXPECTED_VALUE, "evidence_id": RELEVANT_ID},
        ), observation)
        budget = dict(prompt_result.get("budget_diagnostics") or {})
        return {
            "ingestion_accepted_count": sum(bool(item) for item in stored_ids),
            "retrieval_passed": evaluation.retrieval_passed,
            "composition_passed": evaluation.composition_passed,
            "inference_completed": evaluation.inference_passed,
            "value_correct": str((output or {}).get("value", "")) == EXPECTED_VALUE,
            "citation_correct": str((output or {}).get("evidence_id", "")) == RELEVANT_ID,
            "exact_output_correct": output == {"value": EXPECTED_VALUE, "evidence_id": RELEVANT_ID},
            "primary_failure_stage": evaluation.primary_failure_stage,
            "issue_codes": evaluation.issue_codes,
            "prompt_tokens": prompt_result.get("prompt_tokens"),
            "memory_tokens": prompt_result.get("memory_tokens"),
            "compressed": bool(prompt_result.get("compressed")),
            "candidate_memory_count": budget.get("memory_candidate_count"),
            "included_memory_count": budget.get("memory_included_count"),
            "excluded_memory_count": sum(dict(budget.get("excluded_item_counts") or {}).values()),
            "memory_starved": bool(budget.get("memory_starved")),
            "seed_status": model_meta["seed_status"], "latency_ms": model_meta["latency_ms"],
            "error_type": model_meta["error_type"],
        }
    finally:
        memory.close()


def run_experiment(engine: Any, *, memory_root: Path, seed: int = 89) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    observations = []
    for case in cases():
        conditions = {
            condition: _run_condition(
                engine, case=case, memory_root=memory_root / condition / case.case_id,
                policy_enabled=enabled, seed=seed,
            )
            for condition, enabled in (("policy_off", False), ("policy_on", True))
        }
        off = conditions["policy_off"]
        on = conditions["policy_on"]
        observations.append({
            "case_id": case.case_id, "total_prompt_tokens": case.total_prompt_tokens,
            "reserve_output_tokens": RESERVE_OUTPUT_TOKENS, "memory_count": case.memory_count,
            "policy_on_inclusion_delta": on["included_memory_count"] - off["included_memory_count"],
            "conditions": conditions,
        })

    reference = [item for item in observations if item["total_prompt_tokens"] == max(BUDGETS)]
    reference_exact = all(
        item["conditions"][condition]["exact_output_correct"]
        for item in reference for condition in ("policy_off", "policy_on")
    )
    relevant_composed = all(
        item["conditions"][condition]["composition_passed"]
        for item in observations for condition in ("policy_off", "policy_on")
    )
    pressure_observed = any(item["policy_on_inclusion_delta"] < 0 for item in observations)
    return {
        "schema_version": 1, "profile": PROFILE, "profile_version": PROFILE_VERSION,
        "suite_digest": suite_digest(), "started_at": started.isoformat().replace("+00:00", "Z"),
        "finished_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model_label": Path(str(getattr(engine, "model", "unreported"))).name,
        "seed_requested": seed, "thinking_requested": False, "oracle_or_llm_judge_used": False,
        "case_count_per_condition": len(cases()), "live_call_maximum": len(cases()) * 2,
        "acceptance_gate": {
            "require_relevant_composed_in_all_conditions": True,
            "require_reference_budget_exact_output": True,
            "relevant_composed_in_all_conditions": relevant_composed,
            "reference_budget_exact_output": reference_exact,
            "passed": relevant_composed and reference_exact,
        },
        "pressure_observed": pressure_observed,
        "observations": observations,
        "privacy": {
            "raw_prompts_retained": False, "raw_memories_retained": False,
            "raw_outputs_retained": False, "endpoint_retained": False,
        },
        "interpretation_limit": (
            "Nine synthetic budget-density pairs with fixed ranked retrieval; measures word-count prompt packing, "
            "not tokenizer-exact capacity or field workload prevalence."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True); parser.add_argument("--base-url", required=True)
    parser.add_argument("--artifact", type=Path, required=True); parser.add_argument("--seed", type=int, default=89)
    args = parser.parse_args(argv); target = prepare_new_artifact_path(args.artifact)
    engine = EngineFactory.create(
        "openai", model=args.model, base_url=args.base_url, api_key="not-required", is_cloud=False,
    )
    with tempfile.TemporaryDirectory(prefix="engram-trust-prompt-pressure-") as tmp:
        body = run_experiment(engine, memory_root=Path(tmp), seed=args.seed)
    target.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in body.items() if key != "observations"}, indent=2, sort_keys=True))
    return 0 if body["acceptance_gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Paired legacy-versus-temporal Engram validation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

from engram import ProjectMemory, observation_from_engram
from llm_engines import ChatMessage
from llm_engines.contracts import GenerationRequest
from llm_engines.factory import EngineFactory
from llm_harness_core import (
    MemoryCaseSpec,
    build_memory_experiment_body,
    evaluate_memory_case,
    prepare_new_artifact_path,
    summarize_memory_evaluations,
)


PROFILE = "examples.engram_temporal_ab"
PROFILE_VERSION = 1
PROMPT_BUDGET = 520


@dataclass(frozen=True)
class Event:
    evidence_id: str
    text: str
    action: str


@dataclass(frozen=True)
class Query:
    query_id: str
    question: str
    expected_value: str
    expected_evidence_id: str
    forbidden_current_ids: tuple[str, ...] = ()
    historical: bool = False


@dataclass(frozen=True)
class Timeline:
    timeline_id: str
    topic_key: str
    events: tuple[Event, ...]
    queries: tuple[Query, ...]


def timelines() -> tuple[Timeline, ...]:
    return (
        Timeline(
            "atlas",
            "atlas::region",
            (
                Event("EVT-ATLAS-1", "[EVT-ATLAS-1] Atlas deployment region was us-east-1.", "set"),
                Event(
                    "EVT-ATLAS-2",
                    "[EVT-ATLAS-2] Atlas deployment region is now eu-central-1; EVT-ATLAS-1 is obsolete.",
                    "update",
                ),
            ),
            (
                Query(
                    "atlas_current",
                    "What is Atlas's current deployment region?",
                    "eu-central-1",
                    "EVT-ATLAS-2",
                    ("EVT-ATLAS-1",),
                ),
                Query(
                    "atlas_historical",
                    "What was Atlas's deployment region before the update?",
                    "us-east-1",
                    "EVT-ATLAS-1",
                    historical=True,
                ),
            ),
        ),
        Timeline(
            "beacon",
            "beacon::retention",
            (
                Event("EVT-BEACON-1", "[EVT-BEACON-1] Beacon retention period was 45 days.", "set"),
                Event(
                    "EVT-BEACON-2",
                    "[EVT-BEACON-2] Retraction: Beacon has no current retention period; EVT-BEACON-1 is withdrawn.",
                    "retract",
                ),
            ),
            (
                Query(
                    "beacon_current",
                    "What is Beacon's current retention period?",
                    "UNKNOWN",
                    "EVT-BEACON-2",
                    ("EVT-BEACON-1",),
                ),
                Query(
                    "beacon_historical",
                    "What was Beacon's retention period before the retraction?",
                    "45 days",
                    "EVT-BEACON-1",
                    historical=True,
                ),
            ),
        ),
        Timeline(
            "delta",
            "delta::window",
            (
                Event("EVT-DELTA-1", "[EVT-DELTA-1] Delta maintenance time was 01:00 UTC.", "set"),
                Event(
                    "EVT-DELTA-2",
                    "[EVT-DELTA-2] Delta maintenance time is now 03:30 UTC; EVT-DELTA-1 is obsolete.",
                    "update",
                ),
            ),
            (
                Query(
                    "delta_current",
                    "What is Delta's current maintenance time?",
                    "03:30 UTC",
                    "EVT-DELTA-2",
                    ("EVT-DELTA-1",),
                ),
            ),
        ),
    )


def suite_digest() -> str:
    def encode(timeline: Timeline) -> dict[str, Any]:
        return {
            "timeline_id": timeline.timeline_id,
            "topic_key": timeline.topic_key,
            "events": [event.__dict__ for event in timeline.events],
            "queries": [query.__dict__ for query in timeline.queries],
        }

    raw = json.dumps([encode(item) for item in timelines()], sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _generate(engine: Any, prompt: str, seed: int) -> tuple[dict[str, str] | None, dict[str, Any]]:
    try:
        response = engine.generate(
            GenerationRequest(
                messages=[ChatMessage(role="user", content=prompt)],
                temperature=0,
                seed=seed,
                thinking=False,
                max_tokens=96,
                json_schema={
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "evidence_id": {"type": "string"},
                    },
                    "required": ["value", "evidence_id"],
                    "additionalProperties": False,
                },
            )
        )
        parsed = json.loads(response.text)
        return {"value": str(parsed["value"]), "evidence_id": str(parsed["evidence_id"])}, {
            "status": "completed",
            "seed_status": response.seed_status,
            "latency_ms": response.usage.latency_ms,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "error_type": None,
        }
    except Exception as exc:
        return None, {
            "status": "error",
            "seed_status": None,
            "latency_ms": None,
            "input_tokens": None,
            "output_tokens": None,
            "error_type": type(exc).__name__,
        }


def run_experiment(engine: Any, *, memory_root: Path, seed: int = 59) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    evaluations_by_arm: dict[str, list[Any]] = {"legacy": [], "temporal": []}
    observations: list[dict[str, Any]] = []
    for arm in ("legacy", "temporal"):
        for timeline in timelines():
            memory = ProjectMemory(
                base_dir=memory_root / arm / timeline.timeline_id,
                project_id=timeline.timeline_id,
                session_id="seed",
                enable_semantic_graph=False,
                total_prompt_tokens=PROMPT_BUDGET,
            )
            stored = []
            try:
                for event in timeline.events:
                    metadata = {"evidence_id": event.evidence_id}
                    if arm == "temporal":
                        episode_id = memory.store_temporal_episode(
                            event.text,
                            topic_key=timeline.topic_key,
                            action=event.action,
                            metadata=metadata,
                            importance=1.0,
                            bypass_filter=True,
                        )
                    else:
                        episode_id = memory.store_episode(
                            event.text,
                            metadata=metadata,
                            importance=1.0,
                            bypass_filter=True,
                            bypass_dedup=True,
                        )
                    stored.append(bool(episode_id))
            finally:
                memory.close()
            memory = ProjectMemory(
                base_dir=memory_root / arm / timeline.timeline_id,
                project_id=timeline.timeline_id,
                session_id="probe",
                enable_semantic_graph=False,
                total_prompt_tokens=PROMPT_BUDGET,
            )
            try:
                for query in timeline.queries:
                    retrieved = memory.search_episodes(
                        query.question,
                        n=5,
                        include_historical=query.historical,
                    )
                    prompt_result = memory.build_prompt(
                        "Return JSON only. Apply updates and retractions chronologically. If no current value "
                        "exists, value must be UNKNOWN. evidence_id must identify the event establishing the "
                        "answer.\nQuestion: " + query.question,
                        query=query.question,
                        max_prompt_tokens=PROMPT_BUDGET,
                        reserve_output_tokens=96,
                        return_trace=True,
                    )
                    output, model_meta = _generate(engine, str(prompt_result["prompt"]), seed)
                    observation = observation_from_engram(
                        stored_count=sum(stored),
                        retrieved_items=retrieved,
                        prompt_result=prompt_result,
                        observed_output=output,
                        inference_status=model_meta["status"],
                        error_type=model_meta["error_type"],
                    )
                    spec = MemoryCaseSpec(
                        case_id=f"{arm}:{query.query_id}",
                        expected_storage_count=len(timeline.events),
                        required_evidence_ids=(query.expected_evidence_id,),
                        forbidden_prompt_ids=query.forbidden_current_ids,
                        expected_output={
                            "value": query.expected_value,
                            "evidence_id": query.expected_evidence_id,
                        },
                    )
                    evaluation = evaluate_memory_case(spec, observation)
                    evaluations_by_arm[arm].append(evaluation)
                    observations.append(
                        {
                            "arm": arm,
                            "query_id": query.query_id,
                            "historical": query.historical,
                            "selected_evidence_ids": observation.prompt_evidence_ids,
                            "obsolete_in_prompt": any(
                                item in observation.prompt_evidence_ids
                                for item in query.forbidden_current_ids
                            ),
                            "prompt_tokens": prompt_result.get("prompt_tokens"),
                            "memory_tokens": prompt_result.get("memory_tokens"),
                            "memory_starved": observation.diagnostics["budget"].get(
                                "memory_starved"
                            ),
                            "primary_failure_stage": evaluation.primary_failure_stage,
                            "issue_codes": evaluation.issue_codes,
                            "end_to_end_passed": evaluation.end_to_end_passed,
                            "seed_status": model_meta["seed_status"],
                            "latency_ms": model_meta["latency_ms"],
                            "error_type": model_meta["error_type"],
                        }
                    )
            finally:
                memory.close()
    all_evaluations = evaluations_by_arm["legacy"] + evaluations_by_arm["temporal"]
    body = build_memory_experiment_body(
        profile=PROFILE,
        profile_version=PROFILE_VERSION,
        evaluations=all_evaluations,
        retain_diagnostics=True,
    )
    body.update(
        {
            "suite_digest": suite_digest(),
            "started_at": started.isoformat().replace("+00:00", "Z"),
            "finished_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "model_label": Path(str(getattr(engine, "model", "unreported"))).name,
            "seed_requested": seed,
            "thinking_requested": False,
            "prompt_budget": PROMPT_BUDGET,
            "arm_summaries": {
                arm: summarize_memory_evaluations(items)
                for arm, items in evaluations_by_arm.items()
            },
            "current_obsolete_prompt_counts": {
                arm: sum(
                    o["obsolete_in_prompt"]
                    for o in observations
                    if o["arm"] == arm and not o["historical"]
                )
                for arm in ("legacy", "temporal")
            },
            "observations": observations,
            "interpretation_limit": "Three frozen synthetic timelines and five queries per arm; paired mechanism validation, not a general quality estimate.",
        }
    )
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=59)
    args = parser.parse_args(argv)
    target = prepare_new_artifact_path(args.artifact)
    engine = EngineFactory.create(
        "openai", model=args.model, base_url=args.base_url, api_key="not-required", is_cloud=False
    )
    with tempfile.TemporaryDirectory(prefix="engram-temporal-ab-") as tmp:
        body = run_experiment(engine, memory_root=Path(tmp), seed=args.seed)
    target.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in body.items() if k not in {"evaluations", "observations"}},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

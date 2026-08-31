"""Frozen, oracle-free longitudinal knowledge-update probe for Engram."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any

from engram import ProjectMemory
from llm_engines import ChatMessage
from llm_engines.contracts import GenerationRequest
from llm_engines.factory import EngineFactory


PROFILE = "examples.engram_longitudinal_update"
PROFILE_VERSION = 1
ID_RE = re.compile(r"EVT-[A-Z]+-[0-9]+")


@dataclass(frozen=True)
class Event:
    event_id: str
    session: int
    text: str


@dataclass(frozen=True)
class Probe:
    probe_id: str
    question: str
    expected_value: str
    expected_evidence_id: str


@dataclass(frozen=True)
class Timeline:
    timeline_id: str
    events: tuple[Event, ...]
    probes: tuple[Probe, ...]


def timelines() -> tuple[Timeline, ...]:
    return (
        Timeline(
            "atlas",
            (
                Event(
                    "EVT-ATLAS-1",
                    1,
                    "[EVT-ATLAS-1] Project Atlas deployment region was set to us-east-1.",
                ),
                Event(
                    "EVT-ATLAS-2",
                    4,
                    "[EVT-ATLAS-2] Correction: Project Atlas deployment region is now eu-central-1; this supersedes EVT-ATLAS-1.",
                ),
            ),
            (
                Probe(
                    "atlas_current",
                    "What is Project Atlas's current deployment region?",
                    "eu-central-1",
                    "EVT-ATLAS-2",
                ),
                Probe(
                    "atlas_historical",
                    "What was Project Atlas's deployment region immediately after session 1?",
                    "us-east-1",
                    "EVT-ATLAS-1",
                ),
            ),
        ),
        Timeline(
            "beacon",
            (
                Event(
                    "EVT-BEACON-1", 1, "[EVT-BEACON-1] Project Beacon retention was set to 90 days."
                ),
                Event(
                    "EVT-BEACON-2",
                    3,
                    "[EVT-BEACON-2] Correction: Project Beacon retention is now 45 days; this supersedes EVT-BEACON-1.",
                ),
                Event(
                    "EVT-BEACON-3",
                    6,
                    "[EVT-BEACON-3] Retraction: the 45-day Project Beacon retention decision is withdrawn. No replacement retention is established.",
                ),
            ),
            (
                Probe(
                    "beacon_current",
                    "What is Project Beacon's current retention period?",
                    "UNKNOWN",
                    "EVT-BEACON-3",
                ),
                Probe(
                    "beacon_historical",
                    "What was Project Beacon's retention period immediately after session 3?",
                    "45 days",
                    "EVT-BEACON-2",
                ),
            ),
        ),
        Timeline(
            "cedar",
            (
                Event(
                    "EVT-CEDAR-1",
                    2,
                    "[EVT-CEDAR-1] Project Cedar escalations were assigned to team BLUE.",
                ),
                Event(
                    "EVT-CEDAR-2",
                    5,
                    "[EVT-CEDAR-2] Update: Project Cedar escalations are now assigned to team ORANGE, replacing BLUE.",
                ),
            ),
            (
                Probe(
                    "cedar_current",
                    "Which team currently handles Project Cedar escalations?",
                    "ORANGE",
                    "EVT-CEDAR-2",
                ),
            ),
        ),
        Timeline(
            "delta",
            (
                Event(
                    "EVT-DELTA-1",
                    1,
                    "[EVT-DELTA-1] Project Delta maintenance was scheduled for 01:00 UTC.",
                ),
                Event(
                    "EVT-DELTA-2",
                    7,
                    "[EVT-DELTA-2] Reschedule: Project Delta maintenance is now at 03:30 UTC; 01:00 UTC is obsolete.",
                ),
            ),
            (
                Probe(
                    "delta_current",
                    "When is Project Delta maintenance currently scheduled?",
                    "03:30 UTC",
                    "EVT-DELTA-2",
                ),
            ),
        ),
        Timeline(
            "ember",
            (
                Event("EVT-EMBER-1", 1, "[EVT-EMBER-1] Project Ember exports used CSV."),
                Event(
                    "EVT-EMBER-2",
                    4,
                    "[EVT-EMBER-2] Project Ember exports now require PARQUET instead of CSV.",
                ),
                Event(
                    "EVT-EMBER-3",
                    8,
                    "[EVT-EMBER-3] Retraction: the Project Ember export-format requirement is withdrawn with no replacement.",
                ),
            ),
            (
                Probe(
                    "ember_current",
                    "Which export format does Project Ember currently require?",
                    "UNKNOWN",
                    "EVT-EMBER-3",
                ),
            ),
        ),
    )


def suite_digest() -> str:
    raw = json.dumps([asdict(item) for item in timelines()], sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _answer(engine: Any, prompt: str, seed: int) -> tuple[str | None, str | None, dict[str, Any]]:
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
        return (
            str(parsed["value"]).strip(),
            str(parsed["evidence_id"]).strip(),
            {
                "status": "completed",
                "seed_status": response.seed_status,
                "latency_ms": response.usage.latency_ms,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "error_type": None,
            },
        )
    except Exception as exc:
        return (
            None,
            None,
            {
                "status": "error",
                "seed_status": None,
                "latency_ms": None,
                "input_tokens": None,
                "output_tokens": None,
                "error_type": type(exc).__name__,
            },
        )


def run_experiment(engine: Any, *, memory_root: Path, seed: int = 41) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    observations: list[dict[str, Any]] = []
    for timeline in timelines():
        root = memory_root / timeline.timeline_id
        stored: dict[str, bool] = {}
        for event in timeline.events:
            memory = ProjectMemory(
                base_dir=root,
                project_id=timeline.timeline_id,
                session_id=f"session-{event.session}",
                enable_semantic_graph=False,
            )
            try:
                stored[event.event_id] = bool(
                    memory.store_episode(
                        event.text,
                        {"ledger_event_id": event.event_id, "session": event.session},
                        importance=1.0,
                        bypass_filter=True,
                        bypass_dedup=True,
                    )
                )
            finally:
                memory.close()
        memory = ProjectMemory(
            base_dir=root,
            project_id=timeline.timeline_id,
            session_id="probe",
            enable_semantic_graph=False,
        )
        try:
            for probe in timeline.probes:
                result = memory.build_prompt(
                    "Return JSON only. Answer from the project memory. Interpret corrections, supersession, "
                    "and retractions chronologically. If no current value remains, use UNKNOWN. The evidence_id "
                    "must be the single ledger event that establishes the answer.\nQuestion: "
                    + probe.question,
                    query=probe.question,
                    max_prompt_tokens=1200,
                    return_trace=True,
                )
                prompt = str(result["prompt"])
                selected_ids = tuple(sorted(set(ID_RE.findall(prompt))))
                value, evidence_id, model_meta = _answer(engine, prompt, seed)
                value_ok = value is not None and value.casefold() == probe.expected_value.casefold()
                evidence_ok = evidence_id == probe.expected_evidence_id
                observations.append(
                    {
                        "timeline_id": timeline.timeline_id,
                        "probe_id": probe.probe_id,
                        "expected_value": probe.expected_value,
                        "expected_evidence_id": probe.expected_evidence_id,
                        "stored_event_count": sum(stored.values()),
                        "expected_event_count": len(timeline.events),
                        "selected_event_ids": selected_ids,
                        "expected_evidence_selected": probe.expected_evidence_id in selected_ids,
                        "observed_value": value,
                        "observed_evidence_id": evidence_id,
                        "value_correct": value_ok,
                        "evidence_correct": evidence_ok,
                        "end_to_end_passed": value_ok
                        and evidence_ok
                        and probe.expected_evidence_id in selected_ids,
                        "prompt_tokens": result.get("prompt_tokens"),
                        "memory_tokens": result.get("memory_tokens"),
                        **model_meta,
                    }
                )
        finally:
            memory.close()
    finished = datetime.now(timezone.utc)
    completed = [item for item in observations if item["status"] == "completed"]
    return {
        "schema_version": 1,
        "profile": PROFILE,
        "profile_version": PROFILE_VERSION,
        "suite_digest": suite_digest(),
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "finished_at": finished.isoformat().replace("+00:00", "Z"),
        "model_label": Path(str(getattr(engine, "model", "unreported"))).name,
        "seed_requested": seed,
        "thinking_requested": False,
        "oracle_or_llm_judge_used": False,
        "probe_count": len(observations),
        "storage_pass_count": sum(
            o["stored_event_count"] == o["expected_event_count"] for o in observations
        ),
        "retrieval_pass_count": sum(o["expected_evidence_selected"] for o in observations),
        "answer_value_pass_count": sum(o["value_correct"] for o in completed),
        "evidence_pass_count": sum(o["evidence_correct"] for o in completed),
        "end_to_end_pass_count": sum(o["end_to_end_passed"] for o in completed),
        "observations": observations,
        "interpretation_limit": "Frozen synthetic longitudinal cases; failures are stage-attributed and are not a general quality estimate.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=41)
    args = parser.parse_args(argv)
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    if args.artifact.exists():
        parser.error(f"artifact already exists: {args.artifact}")
    engine = EngineFactory.create(
        "openai", model=args.model, base_url=args.base_url, api_key="not-required", is_cloud=False
    )
    with tempfile.TemporaryDirectory(prefix="engram-longitudinal-") as tmp:
        body = run_experiment(engine, memory_root=Path(tmp), seed=args.seed)
    args.artifact.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps({k: v for k, v in body.items() if k != "observations"}, indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

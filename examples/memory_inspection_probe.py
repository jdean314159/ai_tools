"""Privacy-bounded Engram + Inspector + remote-engine composition probe."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any

from engram.project_memory import ProjectMemory
from llm_engines.contracts import ChatMessage, GenerationRequest
from llm_engines.factory import EngineFactory
from llm_harness_core import (
    Actor,
    CapabilityClaim,
    CapabilityRequirement,
    DeterminismClaim,
    PrivacyDeclaration,
    PrivacyValidation,
    RecordEnvelope,
    RunArtifact,
    TimeDeclaration,
    TimeValue,
    dump_artifact,
)
from llm_inspector.adapters.engram_adapter import EngramAugmenter
from llm_inspector.augmenters.baseline import BaselineAugmenter
from llm_inspector.core.types import Turn
from llm_inspector.protocols.context_augmenter import AugmentRequest


PROFILE = "examples.memory_inspection_composition"
PROFILE_VERSION = 2
_ID_RE = re.compile(r"MEM-[A-Z]+-[RD]")


@dataclass(frozen=True)
class Case:
    case_id: str
    question: str
    value: str
    distractor_value: str
    relevant_id: str
    distractor_id: str
    relevant_text: str
    distractor_text: str


@dataclass(frozen=True)
class Observation:
    case_id: str
    condition: str
    status: str
    observed_value: str | None
    observed_memory_id: str | None
    selected_memory_ids: tuple[str, ...]
    relevant_selected: bool
    distractor_selected: bool
    relevant_in_prompt: bool
    correct: bool
    distractor_used: bool
    seed_status: str | None
    latency_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    error_type: str | None = None


def cases() -> tuple[Case, ...]:
    rows = (
        (
            "atlas_region",
            "What is Project Atlas's deployment region?",
            "eu-central-1",
            "us-west-2",
            "MEM-ATLAS-R",
            "MEM-ATLAS-D",
        ),
        (
            "beacon_retention",
            "What retention period applies to Project Beacon?",
            "45 days",
            "90 days",
            "MEM-BEACON-R",
            "MEM-BEACON-D",
        ),
        (
            "cedar_escalation",
            "Which team handles Project Cedar escalations?",
            "ORANGE",
            "BLUE",
            "MEM-CEDAR-R",
            "MEM-CEDAR-D",
        ),
        (
            "delta_window",
            "When is Project Delta's maintenance window?",
            "03:30 UTC",
            "01:00 UTC",
            "MEM-DELTA-R",
            "MEM-DELTA-D",
        ),
        (
            "ember_format",
            "Which export format does Project Ember currently require?",
            "PARQUET",
            "CSV",
            "MEM-EMBER-R",
            "MEM-EMBER-D",
        ),
    )
    return tuple(
        Case(
            *row,
            f"[{row[4]}] Current authoritative fact: {row[1]} Answer: {row[2]}.",
            f"[{row[5]}] Superseded draft, do not use: {row[1]} Old answer: {row[3]}.",
        )
        for row in rows
    )


def suite_digest() -> str:
    payload = json.dumps([asdict(case) for case in cases()], sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _instruction(question: str) -> str:
    return (
        "Answer only from supplied context. If it does not establish the answer, "
        "use value UNKNOWN and memory_id NONE. Prefer a current authoritative fact "
        "over a superseded draft.\nQuestion: " + question
    )


def _prompt_from_trace(trace: Any) -> str:
    final = [section.text for section in trace.context.sections if section.origin == "prompt"]
    if len(final) != 1:
        raise ValueError("Inspector trace must contain exactly one final prompt section")
    return str(final[0])


def _selected_ids(trace: Any) -> tuple[str, ...]:
    found = {match for item in trace.context.evidence for match in _ID_RE.findall(item.text)}
    return tuple(sorted(found))


def _run(
    engine: Any, case: Case, condition: str, prompt: str, trace: Any, seed: int
) -> Observation:
    selected = _selected_ids(trace)
    relevant_in_prompt = case.relevant_id in prompt
    try:
        response = engine.generate(
            GenerationRequest(
                messages=[ChatMessage(role="user", content=prompt)],
                max_tokens=96,
                temperature=0,
                thinking=False,
                seed=seed,
                json_schema={
                    "type": "object",
                    "properties": {"value": {"type": "string"}, "memory_id": {"type": "string"}},
                    "required": ["value", "memory_id"],
                    "additionalProperties": False,
                },
            )
        )
        parsed = json.loads(response.text)
        value = str(parsed.get("value", "")).strip()
        memory_id = str(parsed.get("memory_id", "")).strip()
        baseline = condition == "baseline"
        correct = (
            (value.upper() == "UNKNOWN" and memory_id.upper() == "NONE")
            if baseline
            else (value.casefold() == case.value.casefold() and memory_id == case.relevant_id)
        )
        distractor_used = (
            value.casefold() == case.distractor_value.casefold() or memory_id == case.distractor_id
        )
        return Observation(
            case.case_id,
            condition,
            "completed",
            value,
            memory_id,
            selected,
            case.relevant_id in selected,
            case.distractor_id in selected,
            relevant_in_prompt,
            correct,
            distractor_used,
            response.seed_status,
            response.usage.latency_ms,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
    except Exception as exc:
        return Observation(
            case.case_id,
            condition,
            "error",
            None,
            None,
            selected,
            case.relevant_id in selected,
            case.distractor_id in selected,
            relevant_in_prompt,
            False,
            False,
            None,
            None,
            None,
            None,
            type(exc).__name__,
        )


def run_experiment(engine: Any, *, seed: int = 23, memory_root: Path) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    observations: list[Observation] = []
    baseline_augmenter = BaselineAugmenter(system_prompt="Use only supplied context.")
    for case in cases():
        req = AugmentRequest(
            Turn("user", _instruction(case.question), case.case_id), session_id=case.case_id
        )
        trace = baseline_augmenter.augment(req)
        prompt = "\n\n".join(f"## {s.title}\n{s.text}" for s in trace.context.sections)
        observations.append(_run(engine, case, "baseline", prompt, trace, seed))

    for case in cases():
        project_dir = memory_root / case.case_id
        memory = ProjectMemory(
            base_dir=project_dir,
            project_id=case.case_id,
            session_id="seed",
            enable_semantic_graph=False,
        )
        try:
            memory.store_episode(
                case.relevant_text,
                {"memory_id": case.relevant_id},
                importance=1.0,
                bypass_filter=True,
            )
            memory.store_episode(
                case.distractor_text,
                {"memory_id": case.distractor_id},
                importance=0.8,
                bypass_filter=True,
            )
        finally:
            memory.close()
        augmenter = EngramAugmenter(
            base_dir=project_dir, project_id=case.case_id, project_type="programming_assistant"
        )
        req = AugmentRequest(
            Turn("user", _instruction(case.question), "probe"),
            query=case.question,
            session_id="probe",
        )
        trace = augmenter.augment(req)
        prompt = _prompt_from_trace(trace)
        observations.append(_run(engine, case, "memory", prompt, trace, seed))

    by_case = {case.case_id: case for case in cases()}
    paired = 0
    for case_id in by_case:
        baseline = next(
            o for o in observations if o.case_id == case_id and o.condition == "baseline"
        )
        memory = next(o for o in observations if o.case_id == case_id and o.condition == "memory")
        paired += bool(
            baseline.correct
            and memory.correct
            and memory.relevant_selected
            and memory.relevant_in_prompt
            and not memory.distractor_used
        )
    finished = datetime.now(timezone.utc)
    return {
        "schema_version": 1,
        "profile": PROFILE,
        "profile_version": PROFILE_VERSION,
        "suite_digest": suite_digest(),
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "finished_at": finished.isoformat().replace("+00:00", "Z"),
        "model_label": Path(str(getattr(engine, "model", "unreported"))).name,
        "thinking_requested": False,
        "seed_requested": seed,
        "condition_order": "all_baseline_then_all_memory",
        "case_count": len(by_case),
        "prior_unretained_attempts": 2,
        "paired_success_count": paired,
        "memory_correct_count": sum(o.correct for o in observations if o.condition == "memory"),
        "baseline_safe_count": sum(o.correct for o in observations if o.condition == "baseline"),
        "distractor_used_count": sum(o.distractor_used for o in observations),
        "observations": [asdict(o) for o in observations],
        "interpretation_limit": "Five fixed synthetic cases; not a general memory or model quality estimate.",
    }


def build_artifact(body: dict[str, Any]) -> RunArtifact:
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return RunArtifact(
        RecordEnvelope(
            kind="experiment",
            envelope_schema_version=1,
            body_version=1,
            profile=PROFILE,
            profile_version=PROFILE_VERSION,
            record_id=f"mi_{digest[:32]}",
            lifecycle="final",
            relationships=(),
            attachments=(),
            actors=(Actor("memory-inspection-runner", "recorder", PROFILE, "1"),),
            time=TimeDeclaration(
                TimeValue("value", body["started_at"], "runner"),
                TimeValue("value", body["finished_at"], "runner"),
                TimeValue("value", body["finished_at"], "runner"),
            ),
            privacy=PrivacyDeclaration(
                declared_content_categories=("synthetic_prompt", "synthetic_memory"),
                body_bytes_sensitivity="low; raw interactions omitted",
                transformations_applied=({"operation": "omit_raw_interactions", "version": "1"},),
                validation=PrivacyValidation(
                    "validated",
                    ("no endpoint, raw prompt, response, or memory text",),
                    PROFILE,
                    "synthetic-only",
                    "1",
                    body["finished_at"],
                ),
            ),
            capabilities=(
                CapabilityClaim(
                    "memory_inspection_composition",
                    (
                        CapabilityRequirement("external_service", "model_endpoint"),
                        CapabilityRequirement("implementation", "engram"),
                        CapabilityRequirement("implementation", "llm_inspector"),
                    ),
                    "live_external",
                    "state_changing",
                    DeterminismClaim(
                        "best_effort",
                        "exercised",
                        ("temperature=0", "seed requested; reproducibility not implied"),
                    ),
                    "1",
                ),
            ),
            execution_environment={"model_label": body["model_label"]},
        ),
        body,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--seed", type=int, default=23)
    parser.add_argument("--artifact", type=Path, required=True)
    args = parser.parse_args(argv)
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    if args.artifact.exists():
        parser.error(f"artifact already exists: {args.artifact}")
    with tempfile.TemporaryFile(dir=args.artifact.parent):
        pass
    engine = EngineFactory.create(
        "openai", model=args.model, base_url=args.base_url, api_key="not-required", is_cloud=False
    )
    with tempfile.TemporaryDirectory(prefix="memory-inspection-") as tmp:
        body = run_experiment(engine, seed=args.seed, memory_root=Path(tmp))
    dump_artifact(build_artifact(body), args.artifact)
    print(
        json.dumps({k: v for k, v in body.items() if k != "observations"}, indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

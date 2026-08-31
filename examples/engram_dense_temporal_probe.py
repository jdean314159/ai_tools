"""Oracle-free Engram temporal retrieval under dense conflict pressure."""

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
from llm_engines.factory import EngineFactory

from examples.engram_longitudinal_update_probe import _answer


PROFILE = "examples.engram_dense_temporal"
PROFILE_VERSION = 1
PROMPT_BUDGET = 420
DISTRACTOR_COUNT = 48
ID_RE = re.compile(r"(?:TARGET|NOISE)-[A-Z]+-[0-9]+")


@dataclass(frozen=True)
class DenseCase:
    case_id: str
    subject: str
    question: str
    expected_value: str
    expected_evidence_id: str
    target_events: tuple[str, ...]


def cases() -> tuple[DenseCase, ...]:
    return (
        DenseCase(
            "atlas_current",
            "deployment region",
            "What is Project Atlas's current deployment region?",
            "eu-central-1",
            "TARGET-ATLAS-2",
            (
                "[TARGET-ATLAS-1] Project Atlas deployment region was us-east-1.",
                "[TARGET-ATLAS-2] Correction: Project Atlas deployment region is now eu-central-1; us-east-1 is obsolete.",
            ),
        ),
        DenseCase(
            "beacon_retracted",
            "retention period",
            "What is Project Beacon's current retention period?",
            "UNKNOWN",
            "TARGET-BEACON-3",
            (
                "[TARGET-BEACON-1] Project Beacon retention period was 90 days.",
                "[TARGET-BEACON-2] Project Beacon retention period changed to 45 days.",
                "[TARGET-BEACON-3] Retraction: Project Beacon has no current retention period; the 45-day decision is withdrawn.",
            ),
        ),
        DenseCase(
            "cedar_current",
            "escalation team",
            "Which team currently handles Project Cedar escalations?",
            "ORANGE",
            "TARGET-CEDAR-2",
            (
                "[TARGET-CEDAR-1] Project Cedar escalation team was BLUE.",
                "[TARGET-CEDAR-2] Update: Project Cedar escalation team is now ORANGE, replacing BLUE.",
            ),
        ),
        DenseCase(
            "delta_historical",
            "maintenance time",
            "What was Project Delta's maintenance time before its latest reschedule?",
            "01:00 UTC",
            "TARGET-DELTA-1",
            (
                "[TARGET-DELTA-1] Project Delta maintenance time was 01:00 UTC.",
                "[TARGET-DELTA-2] Project Delta maintenance time is now 03:30 UTC; 01:00 UTC is historical.",
            ),
        ),
        DenseCase(
            "ember_retracted",
            "export format",
            "Which export format does Project Ember currently require?",
            "UNKNOWN",
            "TARGET-EMBER-3",
            (
                "[TARGET-EMBER-1] Project Ember export format was CSV.",
                "[TARGET-EMBER-2] Project Ember export format changed to PARQUET.",
                "[TARGET-EMBER-3] Retraction: Project Ember has no current export-format requirement.",
            ),
        ),
    )


def distractors(case: DenseCase) -> tuple[str, ...]:
    project = case.case_id.split("_", 1)[0].upper()
    values = (
        "BLUE",
        "ORANGE",
        "CSV",
        "PARQUET",
        "30 days",
        "60 days",
        "us-west-2",
        "ap-south-1",
        "00:30 UTC",
        "04:00 UTC",
    )
    rows = []
    for index in range(DISTRACTOR_COUNT):
        other = chr(ord("F") + (index % 20)) + f"-{index:02d}"
        rows.append(
            f"[NOISE-{project}-{index:02d}] Historical planning note for Project {other}: "
            f"its {case.subject} candidate was {values[index % len(values)]}; this statement is not about Project {project.title()}."
        )
    return tuple(rows)


def suite_digest() -> str:
    payload = [{"case": asdict(case), "distractors": distractors(case)} for case in cases()]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def run_experiment(engine: Any, *, memory_root: Path, seed: int = 43) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    observations = []
    for case in cases():
        root = memory_root / case.case_id
        memory = ProjectMemory(
            base_dir=root,
            project_id=case.case_id,
            session_id="seed",
            enable_semantic_graph=False,
            total_prompt_tokens=PROMPT_BUDGET,
        )
        stored = []
        try:
            # Interleave target events so recency/insertion order alone cannot solve every case.
            all_events = list(distractors(case)[:24]) + list(case.target_events[:-1])
            all_events += list(distractors(case)[24:]) + [case.target_events[-1]]
            for index, text in enumerate(all_events):
                stored.append(
                    bool(
                        memory.store_episode(
                            text,
                            {"sequence": index},
                            importance=0.8 if text.startswith("[NOISE") else 1.0,
                            bypass_filter=True,
                            bypass_dedup=True,
                        )
                    )
                )
        finally:
            memory.close()
        memory = ProjectMemory(
            base_dir=root,
            project_id=case.case_id,
            session_id="probe",
            enable_semantic_graph=False,
            total_prompt_tokens=PROMPT_BUDGET,
        )
        try:
            result = memory.build_prompt(
                "Return JSON only. Use project memory chronologically. Corrections replace earlier values; "
                "retractions leave UNKNOWN unless a later replacement exists. evidence_id must identify the "
                "single event establishing the answer.\nQuestion: " + case.question,
                query=case.question,
                max_prompt_tokens=PROMPT_BUDGET,
                reserve_output_tokens=96,
                return_trace=True,
            )
            prompt = str(result["prompt"])
            selected = tuple(sorted(set(ID_RE.findall(prompt))))
            value, evidence_id, meta = _answer(engine, prompt, seed)
            value_ok = value is not None and value.casefold() == case.expected_value.casefold()
            evidence_ok = evidence_id == case.expected_evidence_id
            evidence_selected = case.expected_evidence_id in selected
            observations.append(
                {
                    "case_id": case.case_id,
                    "expected_value": case.expected_value,
                    "expected_evidence_id": case.expected_evidence_id,
                    "stored_count": sum(stored),
                    "declared_count": len(all_events),
                    "selected_event_ids": selected,
                    "selected_count": len(selected),
                    "expected_evidence_selected": evidence_selected,
                    "observed_value": value,
                    "observed_evidence_id": evidence_id,
                    "value_correct": value_ok,
                    "evidence_correct": evidence_ok,
                    "end_to_end_passed": evidence_selected and value_ok and evidence_ok,
                    "prompt_tokens": result.get("prompt_tokens"),
                    "memory_tokens": result.get("memory_tokens"),
                    **meta,
                }
            )
        finally:
            memory.close()
    finished = datetime.now(timezone.utc)
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
        "case_count": len(observations),
        "distractors_per_case": DISTRACTOR_COUNT,
        "prompt_budget": PROMPT_BUDGET,
        "storage_pass_count": sum(o["stored_count"] == o["declared_count"] for o in observations),
        "retrieval_pass_count": sum(o["expected_evidence_selected"] for o in observations),
        "answer_value_pass_count": sum(o["value_correct"] for o in observations),
        "evidence_pass_count": sum(o["evidence_correct"] for o in observations),
        "end_to_end_pass_count": sum(o["end_to_end_passed"] for o in observations),
        "observations": observations,
        "interpretation_limit": "Five frozen synthetic cases under bounded prompt pressure; not a general quality estimate.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=43)
    args = parser.parse_args(argv)
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    if args.artifact.exists():
        parser.error(f"artifact already exists: {args.artifact}")
    engine = EngineFactory.create(
        "openai", model=args.model, base_url=args.base_url, api_key="not-required", is_cloud=False
    )
    with tempfile.TemporaryDirectory(prefix="engram-dense-temporal-") as tmp:
        body = run_experiment(engine, memory_root=Path(tmp), seed=args.seed)
    args.artifact.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps({k: v for k, v in body.items() if k != "observations"}, indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

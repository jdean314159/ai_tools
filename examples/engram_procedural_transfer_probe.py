"""Frozen, oracle-free procedural experience-transfer probe for Engram."""

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


PROFILE = "examples.engram_procedural_transfer"
PROFILE_VERSION = 1
DISTRACTOR_COUNT = 36
PROMPT_BUDGET = 440
ID_RE = re.compile(r"(?:EXP|NOISE)-[A-Z]+-[0-9]+")


@dataclass(frozen=True)
class ProcedureCase:
    case_id: str
    experience_id: str
    experience: str
    query: str
    expected_action: str


def cases() -> tuple[ProcedureCase, ...]:
    return (
        ProcedureCase("rate_limit", "EXP-RATE-1",
            "[EXP-RATE-1] Prior incident: a partner API returned repeated HTTP 429 responses. Immediate retries prolonged the outage. Exponential backoff with jitter succeeded and was recorded as the approved response.",
            "A different partner API is now returning repeated HTTP 429 responses. Which approved response should be applied?",
            "EXPONENTIAL_BACKOFF_WITH_JITTER"),
        ProcedureCase("schema_drift", "EXP-SCHEMA-1",
            "[EXP-SCHEMA-1] Prior incident: ingestion failed after an upstream unknown-field schema change. Guessing field mappings corrupted records. Refreshing the schema contract and regenerating the mapping succeeded.",
            "A new upstream feed fails because of unknown fields introduced by a schema change. Which proven response should be applied?",
            "REFRESH_SCHEMA_AND_REGENERATE_MAPPING"),
        ProcedureCase("disk_pressure", "EXP-DISK-1",
            "[EXP-DISK-1] Prior incident: a worker failed with critically low disk space. Repeated job retries worsened pressure. Rotating archived logs before retrying restored service.",
            "Another worker has critically low disk space and its job failed. Which proven response should be applied first?",
            "ROTATE_ARCHIVED_LOGS_BEFORE_RETRY"),
        ProcedureCase("clock_skew", "EXP-CLOCK-1",
            "[EXP-CLOCK-1] Prior incident: valid credentials produced signature-not-yet-valid errors because host time was skewed. Rotating keys did not help. Synchronizing the system clock before retrying succeeded.",
            "A second host with valid credentials reports signature-not-yet-valid and has clock skew. Which proven response should be applied?",
            "SYNC_SYSTEM_CLOCK_BEFORE_RETRY"),
        ProcedureCase("batch_oom", "EXP-BATCH-1",
            "[EXP-BATCH-1] Prior incident: a batch worker exhausted accelerator memory midway through a large job. Halving the batch size and resuming from the last checkpoint completed safely.",
            "A new batch worker exhausts accelerator memory midway through its job. Which proven response should be applied?",
            "HALVE_BATCH_AND_RESUME_CHECKPOINT"),
    )


def distractors(case: ProcedureCase) -> tuple[str, ...]:
    topics = ("timeout", "permission denied", "checksum mismatch", "DNS failure", "queue lag", "TLS expiry")
    actions = ("restart the proxy", "rotate credentials", "increase concurrency", "clear the cache", "skip validation", "retry immediately")
    prefix = case.experience_id.split("-")[1]
    return tuple(
        f"[NOISE-{prefix}-{index:02d}] Unrelated Project N{index:02d} incident involved {topics[index % len(topics)]}; "
        f"its local response was to {actions[index % len(actions)]}. This was not the {case.case_id} incident."
        for index in range(DISTRACTOR_COUNT)
    )


def suite_digest() -> str:
    payload = [{"case": asdict(case), "distractors": distractors(case)} for case in cases()]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def run_experiment(engine: Any, *, memory_root: Path, seed: int = 47) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    observations = []
    for case in cases():
        root = memory_root / case.case_id
        memory = ProjectMemory(base_dir=root, project_id=case.case_id, session_id="experience",
                               enable_semantic_graph=False, total_prompt_tokens=PROMPT_BUDGET)
        stored = []
        try:
            items = list(distractors(case)[:18]) + [case.experience] + list(distractors(case)[18:])
            for index, item in enumerate(items):
                stored.append(bool(memory.store_episode(
                    item, {"sequence": index, "source": "incident_record"},
                    importance=1.0 if item == case.experience else 0.75,
                    bypass_filter=True, bypass_dedup=True,
                )))
        finally:
            memory.close()
        memory = ProjectMemory(base_dir=root, project_id=case.case_id, session_id="transfer",
                               enable_semantic_graph=False, total_prompt_tokens=PROMPT_BUDGET)
        try:
            result = memory.build_prompt(
                "Return JSON only. Apply the most relevant successful prior experience to the new analogous "
                "incident. value must be the uppercase action code implied by that experience; evidence_id "
                "must identify the single supporting experience. Do not use unrelated projects.\nQuestion: " + case.query,
                query=case.query, max_prompt_tokens=PROMPT_BUDGET, reserve_output_tokens=96, return_trace=True,
            )
            prompt = str(result["prompt"])
            selected = tuple(sorted(set(ID_RE.findall(prompt))))
            value, evidence_id, meta = _answer(engine, prompt, seed)
            value_ok = value == case.expected_action
            evidence_ok = evidence_id == case.experience_id
            selected_ok = case.experience_id in selected
            observations.append({
                "case_id": case.case_id, "expected_action": case.expected_action,
                "expected_evidence_id": case.experience_id,
                "stored_count": sum(stored), "declared_count": len(items),
                "selected_event_ids": selected, "selected_count": len(selected),
                "expected_evidence_selected": selected_ok,
                "observed_action": value, "observed_evidence_id": evidence_id,
                "action_correct": value_ok, "evidence_correct": evidence_ok,
                "end_to_end_passed": selected_ok and value_ok and evidence_ok,
                "prompt_tokens": result.get("prompt_tokens"), "memory_tokens": result.get("memory_tokens"),
                **meta,
            })
        finally:
            memory.close()
    finished = datetime.now(timezone.utc)
    return {
        "schema_version": 1, "profile": PROFILE, "profile_version": PROFILE_VERSION,
        "suite_digest": suite_digest(), "started_at": started.isoformat().replace("+00:00", "Z"),
        "finished_at": finished.isoformat().replace("+00:00", "Z"),
        "model_label": Path(str(getattr(engine, "model", "unreported"))).name,
        "seed_requested": seed, "thinking_requested": False, "oracle_or_llm_judge_used": False,
        "case_count": len(observations), "distractors_per_case": DISTRACTOR_COUNT,
        "prompt_budget": PROMPT_BUDGET,
        "storage_pass_count": sum(o["stored_count"] == o["declared_count"] for o in observations),
        "retrieval_pass_count": sum(o["expected_evidence_selected"] for o in observations),
        "action_pass_count": sum(o["action_correct"] for o in observations),
        "evidence_pass_count": sum(o["evidence_correct"] for o in observations),
        "end_to_end_pass_count": sum(o["end_to_end_passed"] for o in observations),
        "observations": observations,
        "interpretation_limit": "Five synthetic analogical-transfer cases; tests reuse of retrieved experience, not autonomous rule induction.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True); parser.add_argument("--base-url", required=True)
    parser.add_argument("--artifact", type=Path, required=True); parser.add_argument("--seed", type=int, default=47)
    args = parser.parse_args(argv)
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    if args.artifact.exists():
        parser.error(f"artifact already exists: {args.artifact}")
    engine = EngineFactory.create("openai", model=args.model, base_url=args.base_url,
                                  api_key="not-required", is_cloud=False)
    with tempfile.TemporaryDirectory(prefix="engram-procedural-") as tmp:
        body = run_experiment(engine, memory_root=Path(tmp), seed=args.seed)
    args.artifact.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in body.items() if k != "observations"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

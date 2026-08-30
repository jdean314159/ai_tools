"""Procedural transfer scored with a predeclared atomic action vocabulary."""

from __future__ import annotations

import argparse
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

from examples.engram_procedural_transfer_probe import cases, distractors


PROFILE = "examples.engram_procedural_components"
PROFILE_VERSION = 1
PROMPT_BUDGET = 600
ID_RE = re.compile(r"(?:EXP|NOISE)-[A-Z]+-[0-9]+")
VOCABULARY = (
    "exponential_backoff", "jitter", "refresh_schema_contract", "regenerate_mapping",
    "rotate_archived_logs", "synchronize_system_clock", "halve_batch_size",
    "resume_from_checkpoint", "retry",
)
EXPECTED = {
    "rate_limit": ("exponential_backoff", "jitter", "retry"),
    "schema_drift": ("refresh_schema_contract", "regenerate_mapping", "retry"),
    "disk_pressure": ("rotate_archived_logs", "retry"),
    "clock_skew": ("synchronize_system_clock", "retry"),
    "batch_oom": ("halve_batch_size", "resume_from_checkpoint"),
}


def suite_digest() -> str:
    raw = json.dumps({
        "cases": [{"case_id": c.case_id, "experience_id": c.experience_id,
                   "experience": c.experience, "query": c.query,
                   "distractors": distractors(c)} for c in cases()],
        "vocabulary": VOCABULARY, "expected": EXPECTED,
    }, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _generate(engine: Any, prompt: str, seed: int) -> tuple[tuple[str, ...] | None, str | None, dict[str, Any]]:
    try:
        response = engine.generate(GenerationRequest(
            messages=[ChatMessage(role="user", content=prompt)], temperature=0, seed=seed,
            thinking=False, max_tokens=128, json_schema={
                "type": "object", "properties": {
                    "components": {"type": "array", "items": {"type": "string", "enum": list(VOCABULARY)},
                                   "minItems": 1, "uniqueItems": True},
                    "evidence_id": {"type": "string"},
                }, "required": ["components", "evidence_id"], "additionalProperties": False,
            },
        ))
        parsed = json.loads(response.text)
        components = tuple(str(item) for item in parsed["components"])
        return components, str(parsed["evidence_id"]), {
            "status": "completed", "seed_status": response.seed_status,
            "latency_ms": response.usage.latency_ms, "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens, "error_type": None,
        }
    except Exception as exc:
        return None, None, {"status": "error", "seed_status": None, "latency_ms": None,
                            "input_tokens": None, "output_tokens": None, "error_type": type(exc).__name__}


def run_experiment(engine: Any, *, memory_root: Path, seed: int = 53) -> dict[str, Any]:
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
            vocabulary_text = ", ".join(VOCABULARY)
            result = memory.build_prompt(
                "Return JSON only. Apply the most relevant successful prior experience. Select every required "
                "action component, in execution order, only from this closed vocabulary: " + vocabulary_text +
                ". evidence_id must identify the single supporting experience.\nQuestion: " + case.query,
                query=case.query, max_prompt_tokens=PROMPT_BUDGET, reserve_output_tokens=128, return_trace=True,
            )
            prompt = str(result["prompt"])
            selected = tuple(sorted(set(ID_RE.findall(prompt))))
            components, evidence_id, meta = _generate(engine, prompt, seed)
            expected = EXPECTED[case.case_id]
            components_ok = components == expected
            evidence_ok = evidence_id == case.experience_id
            selected_ok = case.experience_id in selected
            observations.append({
                "case_id": case.case_id, "expected_components": expected,
                "observed_components": components, "expected_evidence_id": case.experience_id,
                "observed_evidence_id": evidence_id, "stored_count": sum(stored),
                "declared_count": len(items), "selected_event_ids": selected,
                "selected_count": len(selected), "expected_evidence_selected": selected_ok,
                "components_correct": components_ok, "evidence_correct": evidence_ok,
                "end_to_end_passed": selected_ok and components_ok and evidence_ok,
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
        "case_count": len(observations), "prompt_budget": PROMPT_BUDGET,
        "storage_pass_count": sum(o["stored_count"] == o["declared_count"] for o in observations),
        "retrieval_pass_count": sum(o["expected_evidence_selected"] for o in observations),
        "component_pass_count": sum(o["components_correct"] for o in observations),
        "evidence_pass_count": sum(o["evidence_correct"] for o in observations),
        "end_to_end_pass_count": sum(o["end_to_end_passed"] for o in observations),
        "observations": observations,
        "interpretation_limit": "Five synthetic cases with a closed component vocabulary; not autonomous rule induction.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True); parser.add_argument("--base-url", required=True)
    parser.add_argument("--artifact", type=Path, required=True); parser.add_argument("--seed", type=int, default=53)
    args = parser.parse_args(argv)
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    if args.artifact.exists(): parser.error(f"artifact already exists: {args.artifact}")
    engine = EngineFactory.create("openai", model=args.model, base_url=args.base_url,
                                  api_key="not-required", is_cloud=False)
    with tempfile.TemporaryDirectory(prefix="engram-procedural-components-") as tmp:
        body = run_experiment(engine, memory_root=Path(tmp), seed=args.seed)
    args.artifact.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in body.items() if k != "observations"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())

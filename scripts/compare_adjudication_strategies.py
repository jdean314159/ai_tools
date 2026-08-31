#!/usr/bin/env python3
"""Compare zero-shot, few-shot, policy-enforced, and deterministic adjudication."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


PHASE_5B_PATH = Path(__file__).with_name("adjudicate_neural_memory_probe.py")
SPEC = importlib.util.spec_from_file_location("phase_5b_probe", PHASE_5B_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load Phase 5B probe from {PHASE_5B_PATH}")
phase5b = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = phase5b
SPEC.loader.exec_module(phase5b)


TRAIT_POLICY = {
    "directly_refuted": {
        "status": "resolved_against",
        "review_required": False,
        "relation": "challenges",
    },
    "mixed_scope": {
        "status": "qualified",
        "review_required": True,
        "relation": "qualifies",
    },
    "unsupported_numeric": {
        "status": "unresolved",
        "review_required": True,
        "relation": "unresolved",
    },
    "untested": {
        "status": "unresolved",
        "review_required": True,
        "relation": "unresolved",
    },
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_policy(policy: dict[str, Any], case: dict[str, Any]) -> None:
    expected_ids = set(case["expected"])
    policy_ids = set(policy["claims"])
    if policy_ids != expected_ids:
        raise ValueError("Policy claims must exactly match the Phase 5B expected claims")
    evidence_ids = {item["evidence_id"] for item in case["evidence"]}
    for candidate_id, rule in policy["claims"].items():
        if rule["trait"] not in TRAIT_POLICY:
            raise ValueError(f"Unknown policy trait for {candidate_id}: {rule['trait']}")
        unknown = set(rule["evidence_ids"]) - evidence_ids
        if unknown:
            raise ValueError(f"Unknown policy evidence for {candidate_id}: {unknown}")
    guidance = " ".join(policy["required_guidance_facts"]).casefold()
    for phrase in ("re-ranking", "disabled", "parked", "default-off", "gate"):
        if phrase not in guidance:
            raise ValueError(f"Policy guidance missing required phrase: {phrase}")


def few_shot_messages(examples: dict[str, Any]) -> tuple[str, str]:
    example_input = {
        "claims": examples["claims"],
        "evidence": examples["evidence"],
    }
    user = (
        "Here is an unrelated adjudication example. Apply its evidence-handling "
        "pattern, not its domain facts.\n\n" + json.dumps(example_input, indent=2)
    )
    assistant = json.dumps(examples["result"], indent=2)
    return user, assistant


def generate_proposal(
    *,
    engine: Any,
    case: dict[str, Any],
    candidates: list[dict[str, Any]],
    examples: dict[str, Any] | None,
) -> tuple[Any, dict[str, Any]]:
    from llm_engines import ChatMessage, GenerationRequest, StructuredOutputHandler

    messages = [ChatMessage(role="system", content=phase5b.SYSTEM_PROMPT)]
    if examples is not None:
        example_user, example_assistant = few_shot_messages(examples)
        messages.extend(
            [
                ChatMessage(role="user", content=example_user),
                ChatMessage(role="assistant", content=example_assistant),
            ]
        )
    messages.append(ChatMessage(role="user", content=phase5b.render_prompt(case, candidates)))
    request = GenerationRequest(
        messages=messages,
        temperature=0.0,
        max_tokens=3000,
        json_schema=phase5b.ProbeResult.model_json_schema(),
    )
    response = engine.generate(request)
    parsed = StructuredOutputHandler.parse_with_details(
        response.text,
        phase5b.ProbeResult,
        strict=True,
        allow_repair=False,
    )
    attempts = 1
    if not parsed.success or parsed.data is None:
        correction = (
            "Your response did not match the required schema. Use only the exact "
            "fields and enum values below. Return the complete corrected JSON "
            "object.\n\n" + phase5b.FORMAT_GUIDE
        )
        retry = GenerationRequest(
            messages=[
                *messages,
                ChatMessage(role="assistant", content=response.text),
                ChatMessage(role="user", content=correction),
            ],
            temperature=0.0,
            max_tokens=3000,
            json_schema=phase5b.ProbeResult.model_json_schema(),
        )
        response = engine.generate(retry)
        parsed = StructuredOutputHandler.parse_with_details(
            response.text,
            phase5b.ProbeResult,
            strict=True,
            allow_repair=False,
        )
        attempts = 2
    if not parsed.success or parsed.data is None:
        raise ValueError(f"Proposal failed schema after correction: {parsed.error}")
    diagnostics = {
        "attempts": attempts,
        "finish_reason": response.finish_reason,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "latency_ms": response.usage.latency_ms,
    }
    return parsed.data, diagnostics


def _policy_rationale(trait: str) -> str:
    return {
        "directly_refuted": (
            "Controlling local evaluation and accepted decision evidence directly "
            "reject this claim in its stated scope."
        ),
        "mixed_scope": (
            "The supplied evidence rejects or parks one application without "
            "refuting the broader or descriptive claim."
        ),
        "unsupported_numeric": (
            "No supplied evidence directly establishes the quantitative benefit."
        ),
        "untested": ("The supplied evidence does not test this distinct claim."),
    }[trait]


def apply_policy(
    proposal: Any | None,
    policy: dict[str, Any],
    case: dict[str, Any],
) -> tuple[Any, list[dict[str, Any]]]:
    evidence_ids = {item["evidence_id"] for item in case["evidence"]}
    proposed_adjudications = (
        {item.candidate_id: item for item in proposal.adjudications} if proposal is not None else {}
    )
    valid_relations = []
    if proposal is not None:
        valid_relations = [
            relation.model_copy(deep=True)
            for relation in proposal.relations
            if relation.candidate_id in policy["claims"] and relation.evidence_id in evidence_ids
        ]
    adjudications = []
    corrections: list[dict[str, Any]] = []
    for candidate_id, rule in policy["claims"].items():
        floor = TRAIT_POLICY[rule["trait"]]
        before = proposed_adjudications.get(candidate_id)
        after = phase5b.ProposedAdjudication(
            candidate_id=candidate_id,
            status=floor["status"],
            current_statement=rule["current_statement"],
            rationale=_policy_rationale(rule["trait"]),
            controlling_evidence_ids=rule["evidence_ids"],
            review_required=floor["review_required"],
        )
        adjudications.append(after)
        before_dump = before.model_dump() if before is not None else None
        after_dump = after.model_dump()
        if proposal is not None and before_dump != after_dump:
            corrections.append(
                {
                    "candidate_id": candidate_id,
                    "before": before_dump,
                    "after": after_dump,
                }
            )
        for evidence_id in rule["evidence_ids"]:
            valid_relations = [
                item
                for item in valid_relations
                if not (item.candidate_id == candidate_id and item.evidence_id == evidence_id)
            ]
            relation = (
                "supersedes"
                if floor["status"] == "resolved_against" and evidence_id.startswith("adr-")
                else floor["relation"]
            )
            valid_relations.append(
                phase5b.ProposedRelation(
                    candidate_id=candidate_id,
                    evidence_id=evidence_id,
                    relation=relation,
                    rationale=_policy_rationale(rule["trait"]),
                )
            )
    result = phase5b.ProbeResult(
        relations=valid_relations,
        adjudications=adjudications,
        current_guidance=" ".join(policy["required_guidance_facts"]),
    )
    if proposal is not None and proposal.current_guidance != result.current_guidance:
        corrections.append(
            {
                "candidate_id": "__current_guidance__",
                "before": proposal.current_guidance,
                "after": result.current_guidance,
            }
        )
    return result, corrections


def arm_record(
    *,
    name: str,
    result: Any,
    case: dict[str, Any],
    policy: dict[str, Any],
    diagnostics: dict[str, Any],
    corrections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    graph = phase5b.validate_result(result, case)
    focal = set(case["expected"])
    evidence = {item["evidence_id"] for item in case["evidence"]}
    valid_relations = [
        item
        for item in result.relations
        if item.candidate_id in focal and item.evidence_id in evidence
    ]
    linked_claims = {item.candidate_id for item in valid_relations}
    expected_pairs = {
        (candidate_id, evidence_id)
        for candidate_id, rule in policy["claims"].items()
        for evidence_id in rule["evidence_ids"]
    }
    actual_pairs = {(item.candidate_id, item.evidence_id) for item in valid_relations}
    return {
        "arm": name,
        "status": graph["status"],
        "error_count": len(graph["errors"]),
        "errors": graph["errors"],
        "diagnostics": diagnostics,
        "policy_correction_count": len(corrections or []),
        "policy_corrections": corrections or [],
        "valid_relation_count": len(valid_relations),
        "claims_with_valid_relations": len(linked_claims),
        "matched_policy_relation_count": len(actual_pairs & expected_pairs),
        "unsupported_relation_count": len(actual_pairs - expected_pairs),
        "graph": graph,
    }


def comparison_decision(arms: dict[str, dict[str, Any]]) -> str:
    if arms["deterministic_only"]["status"] != "pass":
        return "stop: declared policy cannot reproduce the gate"
    if arms["few_shot"]["status"] == "pass":
        return (
            "few-shot improved this case; require a held-out conflict arc before "
            "considering model adjudication"
        )
    if (
        arms["few_shot_policy"]["status"] == "pass"
        and arms["few_shot_policy"]["unsupported_relation_count"]
        > arms["deterministic_only"]["unsupported_relation_count"]
    ):
        return (
            "prefer deterministic-only: policy supplies correctness and the LLM "
            "adds unsupported evidence links"
        )
    return "stop: policy-enforced adjudication cannot satisfy the existing gate"


def run_comparison(
    *,
    case_path: Path,
    candidates_path: Path,
    examples_path: Path,
    policy_path: Path,
    results_path: Path,
    report_path: Path,
    manifest_path: Path,
    backend: str,
    model: str,
    host: str,
) -> dict[str, Any]:
    from llm_engines import get_engine

    case, candidates = phase5b.load_case(case_path, candidates_path)
    examples = load_json(examples_path)
    policy = load_json(policy_path)
    validate_policy(policy, case)
    engine = get_engine(
        backend,
        model,
        host=host,
        think=False,
        keep_alive=-1,
        options={"num_ctx": 16384, "seed": 0},
    )
    zero_result, zero_diagnostics = generate_proposal(
        engine=engine,
        case=case,
        candidates=candidates,
        examples=None,
    )
    few_result, few_diagnostics = generate_proposal(
        engine=engine,
        case=case,
        candidates=candidates,
        examples=examples,
    )
    policy_result, corrections = apply_policy(few_result, policy, case)
    deterministic_result, deterministic_corrections = apply_policy(None, policy, case)
    arms = {
        "zero_shot": arm_record(
            name="zero_shot",
            result=zero_result,
            case=case,
            policy=policy,
            diagnostics=zero_diagnostics,
        ),
        "few_shot": arm_record(
            name="few_shot",
            result=few_result,
            case=case,
            policy=policy,
            diagnostics=few_diagnostics,
        ),
        "few_shot_policy": arm_record(
            name="few_shot_policy",
            result=policy_result,
            case=case,
            policy=policy,
            diagnostics={"source": "few_shot proposal plus policy"},
            corrections=corrections,
        ),
        "deterministic_only": arm_record(
            name="deterministic_only",
            result=deterministic_result,
            case=case,
            policy=policy,
            diagnostics={"source": "policy only"},
            corrections=deterministic_corrections,
        ),
    }
    result_payload = {
        "comparison_version": 1,
        "case_id": case["case_id"],
        "decision": comparison_decision(arms),
        "arms": arms,
    }
    results_path.write_text(
        json.dumps(result_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(render_report(result_payload), encoding="utf-8")
    manifest = {
        "manifest_version": 1,
        "backend": backend,
        "model": model,
        "case_sha256": phase5b.sha256_file(case_path),
        "candidates_sha256": phase5b.sha256_file(candidates_path),
        "examples_sha256": phase5b.sha256_file(examples_path),
        "policy_sha256": phase5b.sha256_file(policy_path),
        "decision": result_payload["decision"],
        "arms": {
            name: {
                "status": arm["status"],
                "error_count": arm["error_count"],
                "policy_correction_count": arm["policy_correction_count"],
                "valid_relation_count": arm["valid_relation_count"],
                "claims_with_valid_relations": arm["claims_with_valid_relations"],
                "matched_policy_relation_count": arm["matched_policy_relation_count"],
                "unsupported_relation_count": arm["unsupported_relation_count"],
            }
            for name, arm in arms.items()
        },
        "results_sha256": phase5b.sha256_file(results_path),
        "report_sha256": phase5b.sha256_file(report_path),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 5C Adjudication Comparison",
        "",
        f"**Decision:** {payload['decision']}",
        "",
        "| Arm | Gate | Errors | Corrections | Matched links | Unsupported links |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, arm in payload["arms"].items():
        lines.append(
            f"| `{name}` | {arm['status']} | {arm['error_count']} | "
            f"{arm['policy_correction_count']} | "
            f"{arm['matched_policy_relation_count']} | "
            f"{arm['unsupported_relation_count']} |"
        )
    for name, arm in payload["arms"].items():
        lines.extend(["", f"## {name}", ""])
        if arm["errors"]:
            lines.extend(f"- {error}" for error in arm["errors"])
        else:
            lines.append("- Gate passed.")
        if arm["policy_corrections"]:
            lines.append(
                f"- Deterministic policy made {len(arm['policy_corrections'])} corrections."
            )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5C comparison")
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--examples", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--backend", default="ollama")
    parser.add_argument("--model", default="qwen3.6:27b")
    parser.add_argument("--host", default="http://localhost:11434")
    args = parser.parse_args(argv)
    try:
        manifest = run_comparison(
            case_path=args.case,
            candidates_path=args.candidates,
            examples_path=args.examples,
            policy_path=args.policy,
            results_path=args.results,
            report_path=args.report,
            manifest_path=args.manifest,
            backend=args.backend,
            model=args.model,
            host=args.host,
        )
    except Exception as exc:
        print(f"Phase 5C comparison failed: {exc}", file=sys.stderr)
        return 1
    print(manifest["decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

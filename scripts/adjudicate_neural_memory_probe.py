#!/usr/bin/env python3
"""Run the focused Phase 5B neural-memory adjudication probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


AUTHORITY_RANK = {
    "conversation_assessment": 1,
    "source_summary": 2,
    "implementation_spec": 3,
    "local_evaluation": 4,
    "accepted_adr": 5,
}


class ProposedRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    evidence_id: str
    relation: Literal[
        "supports",
        "challenges",
        "qualifies",
        "supersedes",
        "unresolved",
    ]
    rationale: str = Field(min_length=10, max_length=800)


class ProposedAdjudication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    status: Literal[
        "supported",
        "qualified",
        "contested",
        "resolved_against",
        "unresolved",
        "historical",
    ]
    current_statement: str = Field(min_length=20, max_length=800)
    rationale: str = Field(min_length=10, max_length=1200)
    controlling_evidence_ids: list[str] = Field(default_factory=list)
    review_required: bool


class ProbeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relations: list[ProposedRelation]
    adjudications: list[ProposedAdjudication]
    current_guidance: str = Field(min_length=30, max_length=1500)


SYSTEM_PROMPT = """You adjudicate a narrow knowledge-history case.

Treat candidate claims as historical assertions, not truth. Treat evidence
records according to their authority and scope. Higher authority controls
current ai_tools guidance only within its stated scope; it does not refute
unrelated descriptions of external architectures.

Use no numeric confidence. Preserve early optimistic claims in history. Distinguish:
- description of the TITANS architecture;
- measured value of the current ai_tools neural adapter;
- unsupported numerical benefit claims;
- broader synthesis-node ideas not tested by the neural evaluation.

Return only schema-constrained JSON."""

FORMAT_GUIDE = """Return exactly this JSON shape:
{
  "relations": [
    {
      "candidate_id": "one supplied claim ID",
      "evidence_id": "one supplied evidence ID",
      "relation": "supports|challenges|qualifies|supersedes|unresolved",
      "rationale": "Why this evidence has that relation in its stated scope."
    }
  ],
  "adjudications": [
    {
      "candidate_id": "one supplied claim ID",
      "status": "supported|qualified|contested|resolved_against|unresolved|historical",
      "current_statement": "Current scoped wording.",
      "rationale": "Evidence-based rationale.",
      "controlling_evidence_ids": ["known evidence ID"],
      "review_required": true
    }
  ],
  "current_guidance": "One string stating current ai_tools guidance."
}
Use no other fields or status values."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def load_case(case_path: Path, candidates_path: Path) -> tuple[dict, list[dict]]:
    case = json.loads(case_path.read_text(encoding="utf-8"))
    candidates = {item["candidate_id"]: item for item in load_jsonl(candidates_path)}
    selected = []
    for claim in case.get("historical_claims", []):
        if not Path(claim["source_path"]).exists():
            raise ValueError(f"Historical claim source missing: {claim['source_path']}")
        selected.append(
            {
                "candidate_id": claim["claim_id"],
                "statement": claim["statement"],
                "scope": claim["scope"],
                "evidence_kind": claim["source_type"],
                "qualifications": [],
                "source_refs": [claim["source_path"]],
            }
        )
    for candidate_id in case["focal_candidate_ids"]:
        if candidate_id not in candidates:
            raise ValueError(f"Focal candidate missing: {candidate_id}")
        selected.append(candidates[candidate_id])
    for evidence in case["evidence"]:
        if evidence["authority"] not in AUTHORITY_RANK:
            raise ValueError(f"Unknown evidence authority: {evidence['authority']}")
        if not Path(evidence["source_path"]).exists():
            raise ValueError(f"Evidence source missing: {evidence['source_path']}")
    return case, selected


def render_prompt(case: dict, candidates: list[dict]) -> str:
    candidate_payload = [
        {
            "candidate_id": item["candidate_id"],
            "statement": item["statement"],
            "scope": item["scope"],
            "evidence_kind": item["evidence_kind"],
            "qualifications": item["qualifications"],
            "historical_source_refs": item["source_refs"],
        }
        for item in candidates
    ]
    evidence_payload = [
        {
            **item,
            "authority_rank": AUTHORITY_RANK[item["authority"]],
        }
        for item in case["evidence"]
    ]
    return (
        "Adjudicate the following neural-memory case.\n\n"
        "Historical candidates:\n"
        + json.dumps(candidate_payload, indent=2)
        + "\n\nCurrent evidence:\n"
        + json.dumps(evidence_payload, indent=2)
        + "\n\nFor every candidate, return one adjudication. Create explicit "
        "relations to relevant evidence. current_guidance must state the current "
        "ai_tools decision without erasing historical claims.\n\n" + FORMAT_GUIDE
    )


def validate_result(result: ProbeResult, case: dict) -> dict[str, Any]:
    focal_order = [item["claim_id"] for item in case.get("historical_claims", [])] + list(
        case["focal_candidate_ids"]
    )
    focal = set(focal_order)
    evidence = {item["evidence_id"]: item for item in case["evidence"]}
    adjudications = {item.candidate_id: item for item in result.adjudications}
    errors: list[str] = []

    if set(adjudications) != focal:
        errors.append("adjudications must cover every focal candidate exactly once")
    for relation in result.relations:
        if relation.candidate_id not in focal:
            errors.append(f"unknown candidate relation: {relation.candidate_id}")
        if relation.evidence_id not in evidence:
            errors.append(f"unknown evidence relation: {relation.evidence_id}")
    for candidate_id, expected_status in case["expected"].items():
        actual = adjudications.get(candidate_id)
        if actual is None or actual.status != expected_status:
            errors.append(
                f"{candidate_id} expected {expected_status}, "
                f"got {actual.status if actual else 'missing'}"
            )
    for candidate_id, expected_review in case.get("expected_review_required", {}).items():
        actual = adjudications.get(candidate_id)
        if actual is None or actual.review_required != expected_review:
            errors.append(
                f"{candidate_id} expected review_required={expected_review}, "
                f"got {actual.review_required if actual else 'missing'}"
            )
    titans_id = "candidate-1daddd4ca13cf45a"
    if adjudications.get(titans_id) and adjudications[titans_id].status == "resolved_against":
        errors.append("TITANS architecture description was incorrectly resolved against")
    for item in result.adjudications:
        unknown = set(item.controlling_evidence_ids) - evidence.keys()
        if unknown:
            errors.append(f"{item.candidate_id} cites unknown controlling evidence")
        if item.status == "resolved_against":
            ranks = [
                AUTHORITY_RANK[evidence[evidence_id]["authority"]]
                for evidence_id in item.controlling_evidence_ids
            ]
            if not ranks or max(ranks) < AUTHORITY_RANK["local_evaluation"]:
                errors.append(f"{item.candidate_id} resolved against without controlling evidence")
    guidance = result.current_guidance.casefold()
    required_guidance = ("re-ranking", "disabled", "parked", "default-off", "gate")
    for phrase in required_guidance:
        if phrase not in guidance:
            errors.append(f"current guidance missing {phrase!r}")
    serialized = result.model_dump_json()
    if "confidence" in serialized.casefold():
        errors.append("numeric or qualitative confidence was introduced")

    relations_by_candidate: dict[str, list[dict]] = {}
    for candidate_id in focal:
        relations_by_candidate[candidate_id] = [
            relation.model_dump()
            for relation in result.relations
            if relation.candidate_id == candidate_id
        ]
    graph = {
        "case_id": case["case_id"],
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "current_guidance": result.current_guidance,
        "claims": [
            {
                **adjudications[candidate_id].model_dump(),
                "historical_claim_preserved": True,
                "relations": relations_by_candidate[candidate_id],
            }
            for candidate_id in focal_order
            if candidate_id in adjudications
        ],
        "evidence": case["evidence"],
    }
    return graph


def run_probe(
    *,
    case_path: Path,
    candidates_path: Path,
    output_path: Path,
    report_path: Path,
    manifest_path: Path,
    backend: str,
    model: str,
    host: str,
) -> dict:
    from llm_engines import ChatMessage, GenerationRequest, StructuredOutputHandler, get_engine

    case, candidates = load_case(case_path, candidates_path)
    engine = get_engine(
        backend,
        model,
        host=host,
        think=False,
        keep_alive=-1,
        options={"num_ctx": 16384, "seed": 0},
    )
    request = GenerationRequest(
        messages=[
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="user", content=render_prompt(case, candidates)),
        ],
        temperature=0.0,
        max_tokens=3000,
        json_schema=ProbeResult.model_json_schema(),
    )
    response = engine.generate(request)
    parsed = StructuredOutputHandler.parse_with_details(
        response.text, ProbeResult, strict=True, allow_repair=False
    )
    attempts = 1
    if not parsed.success or parsed.data is None:
        response = engine.generate(
            GenerationRequest(
                messages=[
                    *request.messages,
                    ChatMessage(role="assistant", content=response.text),
                    ChatMessage(
                        role="user",
                        content=(
                            "Your response did not match the required schema. "
                            "Use only the exact fields and enum values below. "
                            "Return the complete corrected JSON object.\n\n" + FORMAT_GUIDE
                        ),
                    ),
                ],
                temperature=0.0,
                max_tokens=3000,
                json_schema=ProbeResult.model_json_schema(),
            )
        )
        parsed = StructuredOutputHandler.parse_with_details(
            response.text, ProbeResult, strict=True, allow_repair=False
        )
        attempts = 2
    if not parsed.success or parsed.data is None:
        raise ValueError(
            f"Model output failed adjudication schema after correction: {parsed.error}"
        )
    result = parsed.data
    graph = validate_result(result, case)
    output_path.write_text(
        json.dumps(graph, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(render_markdown(graph, candidates), encoding="utf-8")
    manifest = {
        "manifest_version": 1,
        "case_sha256": sha256_file(case_path),
        "candidates_sha256": sha256_file(candidates_path),
        "backend": backend,
        "model": model,
        "finish_reason": response.finish_reason,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "latency_ms": response.usage.latency_ms,
        "attempts": attempts,
        "probe_status": graph["status"],
        "error_count": len(graph["errors"]),
        "graph_sha256": sha256_file(output_path),
        "report_sha256": sha256_file(report_path),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def render_markdown(graph: dict, candidates: list[dict]) -> str:
    by_id = {item["candidate_id"]: item for item in candidates}
    lines = [
        "# Neural-Memory Adjudication Probe",
        "",
        f"Gate: **{graph['status']}**",
        "",
        "## Current Guidance",
        "",
        graph["current_guidance"],
        "",
        "## Claim History",
        "",
    ]
    for claim in graph["claims"]:
        historical = by_id[claim["candidate_id"]]
        lines.extend(
            [
                f"### {claim['candidate_id']}",
                "",
                f"**Historical claim:** {historical['statement']}",
                "",
                f"**Current status:** `{claim['status']}`",
                "",
                f"**Current statement:** {claim['current_statement']}",
                "",
                f"**Rationale:** {claim['rationale']}",
                "",
                f"**Review required:** `{str(claim['review_required']).lower()}`",
                "",
                "**Evidence relations:**",
                "",
            ]
        )
        for relation in claim["relations"]:
            lines.append(
                f"- `{relation['relation']}` `{relation['evidence_id']}`: {relation['rationale']}"
            )
        lines.append("")
    if graph["errors"]:
        lines.extend(["## Gate Errors", ""])
        lines.extend(f"- {error}" for error in graph["errors"])
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5B adjudication probe")
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--backend", default="ollama")
    parser.add_argument("--model", default="qwen3.6:27b")
    parser.add_argument("--host", default="http://localhost:11434")
    args = parser.parse_args(argv)
    try:
        manifest = run_probe(
            case_path=args.case,
            candidates_path=args.candidates,
            output_path=args.output,
            report_path=args.report,
            manifest_path=args.manifest,
            backend=args.backend,
            model=args.model,
            host=args.host,
        )
    except Exception as exc:
        print(f"Adjudication probe failed: {exc}", file=sys.stderr)
        return 1
    print(f"Adjudication probe {manifest['probe_status']}: {manifest['error_count']} gate errors")
    return 0 if manifest["probe_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

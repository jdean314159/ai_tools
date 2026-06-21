#!/usr/bin/env python3
"""Prepare and apply human review decisions for knowledge candidates."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("evaluation", ("evaluat", "benchmark", "metric", "ground truth", "test set")),
    ("memory-context", ("memory", "context", "forget", "episod", "long-term")),
    ("rag-retrieval", ("rag", "retriev", "vector", "embedding", "chunk", "rerank")),
    ("agents", ("agent", "planner", "worker", "tool use", "orchestrat", "multi-agent")),
    ("inference-models", ("inference", "quant", "gpu", "vram", "model", "ollama", "vllm")),
    ("safety-reliability", ("safe", "reliab", "halluc", "security", "guard", "failure")),
    ("architecture", ("architect", "modular", "interface", "contract", "pipeline", "system")),
)
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "with", "on",
    "is", "are", "be", "as", "that", "this", "when", "should", "can", "may",
    "from", "by", "their", "its", "using", "use", "used", "into", "than",
}
MAX_SOURCE_UNIT_CHARS = 20_000


class ReviewedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=20, max_length=600)
    scope: str = Field(min_length=3, max_length=300)
    evidence_kind: Literal["secondary_assessment", "source_material", "mixed"]
    qualifications: list[str] = Field(default_factory=list, max_length=8)


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    recorded_at: str
    reviewer: str = Field(min_length=1, max_length=200)
    action: Literal["approve", "edit", "reject", "defer", "split", "consolidate"]
    candidate_ids: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=3, max_length=2000)
    claims: list[ReviewedClaim] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_action_shape(self) -> "ReviewDecision":
        count = len(self.candidate_ids)
        claim_count = len(self.claims)
        if len(set(self.candidate_ids)) != count:
            raise ValueError("candidate_ids must be unique")
        if self.action == "approve" and (count != 1 or claim_count != 0):
            raise ValueError("approve requires one candidate and no replacement claim")
        if self.action == "edit" and (count != 1 or claim_count != 1):
            raise ValueError("edit requires one candidate and one replacement claim")
        if self.action in {"reject", "defer"} and claim_count != 0:
            raise ValueError(f"{self.action} cannot contain replacement claims")
        if self.action == "split" and (count != 1 or claim_count < 2):
            raise ValueError("split requires one candidate and at least two claims")
        if self.action == "consolidate" and (count < 2 or claim_count != 1):
            raise ValueError(
                "consolidate requires at least two candidates and one claim"
            )
        return self


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if len(token) > 2 and token not in STOPWORDS
    }


def classify_topic(candidate: dict) -> str:
    text = f"{candidate['statement']} {candidate['scope']}".casefold()
    best_topic = "other"
    best_score = 0
    for topic, terms in TOPIC_RULES:
        score = sum(text.count(term) for term in terms)
        if score > best_score:
            best_topic = topic
            best_score = score
    return best_topic


def related_candidates(candidates: list[dict], limit: int = 3) -> dict[str, list[str]]:
    token_sets = {
        item["candidate_id"]: _tokens(f"{item['statement']} {item['scope']}")
        for item in candidates
    }
    result: dict[str, list[str]] = {}
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        source_tokens = token_sets[candidate_id]
        scored: list[tuple[float, str]] = []
        for other in candidates:
            other_id = other["candidate_id"]
            if other_id == candidate_id:
                continue
            other_tokens = token_sets[other_id]
            union = source_tokens | other_tokens
            if not union:
                continue
            score = len(source_tokens & other_tokens) / len(union)
            if score >= 0.18:
                scored.append((score, other_id))
        result[candidate_id] = [
            other_id
            for _, other_id in sorted(scored, key=lambda row: (-row[0], row[1]))[:limit]
        ]
    return result


def _source_units(corpus: list[dict]) -> dict[str, dict]:
    units: dict[str, dict] = {}
    for record_index, record in enumerate(corpus, start=1):
        if (
            record.get("source_kind") != "message_text"
            or record.get("sender") != "assistant"
        ):
            continue
        text = record.get("normalized_text", "")
        part = 0
        for start in range(0, len(text), MAX_SOURCE_UNIT_CHARS):
            end = min(start + MAX_SOURCE_UNIT_CHARS, len(text))
            part += 1
            source_unit_id = f"r{record_index:06d}p{part:03d}"
            units[source_unit_id] = {
                "source_unit_id": source_unit_id,
                "conversation_uuid": record["conversation_uuid"],
                "message_uuid": record["message_uuid"],
                "source_kind": record["source_kind"],
                "char_start": start,
                "char_end": end,
                "text": text[start:end],
            }
    return units


def build_review_queue(
    candidates: list[dict],
    corpus: list[dict],
    *,
    excerpt_chars: int = 1200,
) -> list[dict]:
    units = _source_units(corpus)
    related = related_candidates(candidates)
    queue: list[dict] = []
    for candidate in candidates:
        evidence = []
        for source_ref in candidate["source_refs"]:
            unit = units.get(source_ref)
            if unit is None:
                raise ValueError(f"Candidate cites unknown source unit: {source_ref}")
            excerpt = unit["text"][:excerpt_chars]
            evidence.append(
                {
                    "source_unit_id": source_ref,
                    "conversation_uuid": unit["conversation_uuid"],
                    "message_uuid": unit["message_uuid"],
                    "source_kind": unit["source_kind"],
                    "char_start": unit["char_start"],
                    "char_end": unit["char_end"],
                    "excerpt": excerpt,
                    "excerpt_truncated": len(unit["text"]) > excerpt_chars,
                }
            )
        queue.append(
            {
                **candidate,
                "topic": classify_topic(candidate),
                "related_candidate_ids": related[candidate["candidate_id"]],
                "evidence": evidence,
            }
        )
    # Round-robin conversations within topic so the dominant source does not
    # occupy one uninterrupted review block.
    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for item in queue:
        grouped[item["topic"]][item["conversation_uuid"]].append(item)
    ordered: list[dict] = []
    for topic in sorted(grouped):
        by_conversation = grouped[topic]
        for values in by_conversation.values():
            values.sort(key=lambda item: item["candidate_id"])
        while any(by_conversation.values()):
            for conversation_uuid in sorted(by_conversation):
                if by_conversation[conversation_uuid]:
                    ordered.append(by_conversation[conversation_uuid].pop(0))
    for index, item in enumerate(ordered, start=1):
        item["review_index"] = index
    return ordered


def render_review_html(queue: list[dict], decisions_path: Path) -> str:
    topic_counts = Counter(item["topic"] for item in queue)
    sections = []
    current_topic = None
    for item in queue:
        if item["topic"] != current_topic:
            current_topic = item["topic"]
            sections.append(
                f'<h2 id="topic-{html.escape(current_topic)}">'
                f"{html.escape(current_topic)} ({topic_counts[current_topic]})</h2>"
            )
        qualifications = "".join(
            f"<li>{html.escape(value)}</li>" for value in item["qualifications"]
        )
        related = ", ".join(item["related_candidate_ids"]) or "none"
        evidence = "".join(
            "<details><summary>"
            + html.escape(
                f"{value['source_unit_id']} | message {value['message_uuid']}"
            )
            + "</summary><pre>"
            + html.escape(value["excerpt"])
            + "</pre></details>"
            for value in item["evidence"]
        )
        candidate_id = item["candidate_id"]
        command = (
            "python scripts/review_knowledge_candidates.py decide "
            " --candidates docs/projects/knowledge_mvp/CANDIDATE_CLAIMS.jsonl"
            f" --decisions {decisions_path} --reviewer YOUR_NAME "
            f"--action approve --candidate-id {candidate_id} "
            '--rationale "Human rationale"'
        )
        sections.append(
            f"""
<article id="{html.escape(candidate_id)}">
  <h3>{item['review_index']}. {html.escape(candidate_id)}</h3>
  <p><strong>Statement:</strong> {html.escape(item['statement'])}</p>
  <p><strong>Scope:</strong> {html.escape(item['scope'])}</p>
  <p><strong>Evidence kind:</strong> {html.escape(item['evidence_kind'])}</p>
  <p><strong>Conversation:</strong> {html.escape(item['conversation_uuid'])}</p>
  <p><strong>Qualifications:</strong></p><ul>{qualifications}</ul>
  <p><strong>Related:</strong> {html.escape(related)}</p>
  {evidence}
  <details><summary>Decision command</summary><pre>{html.escape(command)}</pre></details>
</article>"""
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Knowledge Candidate Review</title>
<style>
body{{font-family:sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}}
article{{border:1px solid #bbb;border-radius:6px;padding:1rem;margin:1rem 0}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f5f5;padding:.75rem}}
h2{{border-bottom:2px solid #555;padding-top:2rem}}
</style></head><body>
<h1>Knowledge Candidate Review</h1>
<p>{len(queue)} pending candidates. This file is private and local.</p>
{''.join(sections)}
</body></html>
"""


def prepare_review(
    *,
    candidates_path: Path,
    candidate_manifest_path: Path,
    corpus_path: Path,
    corpus_manifest_path: Path,
    queue_path: Path,
    bundle_path: Path,
    decisions_path: Path,
    review_manifest_path: Path,
) -> dict:
    candidate_manifest = json.loads(
        candidate_manifest_path.read_text(encoding="utf-8")
    )
    corpus_manifest = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
    if sha256_file(candidates_path) != candidate_manifest["candidates_sha256"]:
        raise ValueError("Candidate artifact hash differs from extraction manifest")
    if sha256_file(corpus_path) != corpus_manifest["normalized_corpus_sha256"]:
        raise ValueError("Corpus hash differs from corpus manifest")
    candidates = load_jsonl(candidates_path)
    corpus = load_jsonl(corpus_path)
    if len(candidates) != candidate_manifest["candidate_count"]:
        raise ValueError("Candidate count differs from extraction manifest")
    queue = build_review_queue(candidates, corpus)
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("w", encoding="utf-8", newline="\n") as handle:
        for item in queue:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    bundle_path.write_text(
        render_review_html(queue, decisions_path),
        encoding="utf-8",
    )
    decisions_path.touch(exist_ok=True)
    topic_counts = Counter(item["topic"] for item in queue)
    conversation_counts = Counter(item["conversation_uuid"] for item in queue)
    manifest = {
        "manifest_version": 1,
        "candidate_sha256": sha256_file(candidates_path),
        "corpus_sha256": sha256_file(corpus_path),
        "queue_sha256": sha256_file(queue_path),
        "bundle_sha256": sha256_file(bundle_path),
        "candidate_count": len(queue),
        "topic_counts": dict(sorted(topic_counts.items())),
        "conversation_counts": dict(sorted(conversation_counts.items())),
        "decisions_recorded": len(load_jsonl(decisions_path)),
        "review_complete": False,
        "review_artifacts_are_private": True,
    }
    review_manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def append_decision(path: Path, decision: ReviewDecision, candidates: set[str]) -> None:
    unknown = sorted(set(decision.candidate_ids) - candidates)
    if unknown:
        raise ValueError(f"Unknown candidate IDs: {', '.join(unknown)}")
    existing = load_jsonl(path)
    if any(item.get("event_id") == decision.event_id for item in existing):
        raise ValueError(f"Duplicate event ID: {decision.event_id}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(decision.model_dump(), ensure_ascii=False, sort_keys=True)
            + "\n"
        )


def _latest_decisions(
    decisions: list[ReviewDecision],
) -> dict[str, ReviewDecision]:
    latest: dict[str, ReviewDecision] = {}
    for decision in decisions:
        for candidate_id in decision.candidate_ids:
            latest[candidate_id] = decision
    return latest


def materialize_approved(
    *,
    candidates_path: Path,
    decisions_path: Path,
    approved_path: Path,
    review_manifest_path: Path,
) -> dict:
    candidates = load_jsonl(candidates_path)
    by_id = {item["candidate_id"]: item for item in candidates}
    raw_decisions = load_jsonl(decisions_path)
    decisions = [ReviewDecision.model_validate(item) for item in raw_decisions]
    if len({item.event_id for item in decisions}) != len(decisions):
        raise ValueError("Decision log contains duplicate event IDs")
    for decision in decisions:
        unknown = set(decision.candidate_ids) - by_id.keys()
        if unknown:
            raise ValueError("Decision log contains unknown candidate IDs")
    latest = _latest_decisions(decisions)
    approved: list[dict] = []
    emitted_events: set[str] = set()
    for candidate_id in sorted(latest):
        decision = latest[candidate_id]
        if decision.event_id in emitted_events:
            continue
        if any(
            latest.get(source_id) is None
            or latest[source_id].event_id != decision.event_id
            for source_id in decision.candidate_ids
        ):
            continue
        emitted_events.add(decision.event_id)
        if decision.action in {"reject", "defer"}:
            continue
        source_candidates = [by_id[value] for value in decision.candidate_ids]
        source_refs = sorted(
            {
                ref
                for candidate in source_candidates
                for ref in candidate["source_refs"]
            }
        )
        claims: list[ReviewedClaim]
        if decision.action == "approve":
            source = source_candidates[0]
            claims = [
                ReviewedClaim(
                    statement=source["statement"],
                    scope=source["scope"],
                    evidence_kind=source["evidence_kind"],
                    qualifications=source["qualifications"],
                )
            ]
        else:
            claims = decision.claims
        for claim_index, claim in enumerate(claims, start=1):
            payload = claim.model_dump()
            claim_id = f"claim-{canonical_hash({
                'payload': payload,
                'source_candidates': decision.candidate_ids,
                'claim_index': claim_index,
            })[:16]}"
            approved.append(
                {
                    "schema_version": 1,
                    "claim_id": claim_id,
                    "status": "approved",
                    **payload,
                    "source_candidate_ids": decision.candidate_ids,
                    "source_refs": source_refs,
                    "review_event_id": decision.event_id,
                    "reviewer": decision.reviewer,
                    "review_rationale": decision.rationale,
                    "reviewed_at": decision.recorded_at,
                }
            )
    approved.sort(key=lambda item: item["claim_id"])
    approved_path.parent.mkdir(parents=True, exist_ok=True)
    with approved_path.open("w", encoding="utf-8", newline="\n") as handle:
        for item in approved:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    status_counts = Counter(
        latest[item].action for item in latest
    )
    review_complete = len(latest) == len(candidates) and not any(
        action == "defer" for action in status_counts
    )
    manifest = json.loads(review_manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "decisions_sha256": sha256_file(decisions_path),
            "decisions_recorded": len(decisions),
            "candidates_decided": len(latest),
            "decision_counts": dict(sorted(status_counts.items())),
            "approved_claim_count": len(approved),
            "approved_claims_sha256": sha256_file(approved_path),
            "review_complete": review_complete,
        }
    )
    review_manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _reviewed_claim_from_args(args: argparse.Namespace) -> ReviewedClaim:
    return ReviewedClaim(
        statement=args.statement,
        scope=args.scope,
        evidence_kind=args.evidence_kind,
        qualifications=args.qualification or [],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Human review workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--candidates", type=Path, required=True)
    prepare.add_argument("--candidate-manifest", type=Path, required=True)
    prepare.add_argument("--corpus", type=Path, required=True)
    prepare.add_argument("--corpus-manifest", type=Path, required=True)
    prepare.add_argument("--queue", type=Path, required=True)
    prepare.add_argument("--bundle", type=Path, required=True)
    prepare.add_argument("--decisions", type=Path, required=True)
    prepare.add_argument("--manifest", type=Path, required=True)

    decide = subparsers.add_parser("decide")
    decide.add_argument("--candidates", type=Path, required=True)
    decide.add_argument("--decisions", type=Path, required=True)
    decide.add_argument("--reviewer", required=True)
    decide.add_argument(
        "--action",
        choices=("approve", "edit", "reject", "defer", "split", "consolidate"),
        required=True,
    )
    decide.add_argument("--candidate-id", action="append", required=True)
    decide.add_argument("--rationale", required=True)
    decide.add_argument("--statement")
    decide.add_argument("--scope")
    decide.add_argument(
        "--evidence-kind",
        choices=("secondary_assessment", "source_material", "mixed"),
    )
    decide.add_argument("--qualification", action="append")
    decide.add_argument(
        "--claims-json",
        type=Path,
        help="JSON file containing a list of replacement claim objects.",
    )

    materialize = subparsers.add_parser("materialize")
    materialize.add_argument("--candidates", type=Path, required=True)
    materialize.add_argument("--decisions", type=Path, required=True)
    materialize.add_argument("--approved", type=Path, required=True)
    materialize.add_argument("--manifest", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            manifest = prepare_review(
                candidates_path=args.candidates,
                candidate_manifest_path=args.candidate_manifest,
                corpus_path=args.corpus,
                corpus_manifest_path=args.corpus_manifest,
                queue_path=args.queue,
                bundle_path=args.bundle,
                decisions_path=args.decisions,
                review_manifest_path=args.manifest,
            )
            print(f"Prepared {manifest['candidate_count']} review candidates")
        elif args.command == "decide":
            candidates = {
                item["candidate_id"] for item in load_jsonl(args.candidates)
            }
            replacement_actions = {"edit", "split", "consolidate"}
            claims = []
            if args.action in replacement_actions:
                if args.claims_json:
                    raw_claims = json.loads(
                        args.claims_json.read_text(encoding="utf-8")
                    )
                    if not isinstance(raw_claims, list):
                        raise ValueError("claims-json must contain a JSON list")
                    claims = [
                        ReviewedClaim.model_validate(item) for item in raw_claims
                    ]
                else:
                    if not (args.statement and args.scope and args.evidence_kind):
                        raise ValueError(
                            "Replacement actions require claims-json or statement, "
                            "scope, and evidence-kind"
                        )
                    claims = [_reviewed_claim_from_args(args)]
            decision = ReviewDecision(
                event_id=f"review-{uuid.uuid4().hex}",
                recorded_at=datetime.now(timezone.utc).isoformat(),
                reviewer=args.reviewer,
                action=args.action,
                candidate_ids=args.candidate_id,
                rationale=args.rationale,
                claims=claims,
            )
            append_decision(args.decisions, decision, candidates)
            print(f"Recorded {decision.action}: {decision.event_id}")
        else:
            manifest = materialize_approved(
                candidates_path=args.candidates,
                decisions_path=args.decisions,
                approved_path=args.approved,
                review_manifest_path=args.manifest,
            )
            print(
                f"Materialized {manifest['approved_claim_count']} approved claims; "
                f"review_complete={manifest['review_complete']}"
            )
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        print(f"Review workflow failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

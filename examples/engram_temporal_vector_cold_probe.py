"""Cold-reopen validation for temporal Engram with real vector retrieval."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from engram import EmbeddingService, ProjectMemory, Telemetry
from llm_harness_core import prepare_new_artifact_path


PROFILE = "examples.engram_temporal_vector_cold"
PROFILE_VERSION = 1


@dataclass(frozen=True)
class Case:
    case_id: str
    topic_key: str
    old_id: str
    current_id: str
    old_text: str
    current_text: str
    current_action: str
    current_query: str
    historical_query: str


def cases() -> tuple[Case, ...]:
    return (
        Case(
            "atlas",
            "atlas::region",
            "CTV-ATLAS-1",
            "CTV-ATLAS-2",
            "Atlas workloads previously deployed in the Virginia us-east-1 cloud region.",
            "Atlas workloads now deploy in Frankfurt using the eu-central-1 cloud region.",
            "update",
            "Where do Atlas workloads currently deploy?",
            "Where did Atlas workloads deploy before the region update?",
        ),
        Case(
            "beacon",
            "beacon::retention",
            "CTV-BEACON-1",
            "CTV-BEACON-2",
            "Beacon audit records previously had a forty-five day retention period.",
            "Beacon currently has no audit retention period because that requirement was retracted.",
            "retract",
            "What is Beacon's current audit retention period?",
            "What was Beacon's audit retention period before the retraction?",
        ),
        Case(
            "delta",
            "delta::window",
            "CTV-DELTA-1",
            "CTV-DELTA-2",
            "Delta maintenance previously started at one o'clock UTC.",
            "Delta maintenance now starts at half past three UTC.",
            "update",
            "When does Delta maintenance currently start?",
            "When did Delta maintenance start before the schedule update?",
        ),
    )


def suite_digest() -> str:
    raw = json.dumps([asdict(case) for case in cases()], sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _ids(items: list[Any]) -> tuple[str, ...]:
    return tuple(str(getattr(item, "metadata", {}).get("evidence_id")) for item in items)


def _prompt_ids(result: dict[str, Any]) -> tuple[str, ...]:
    ids = []
    for evidence in result["trace"].evidence:
        evidence_id = evidence.meta.get("evidence_id")
        if evidence_id and evidence_id not in ids:
            ids.append(str(evidence_id))
    return tuple(ids)


def run(root: Path) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    embedder = EmbeddingService.sentence_transformers(model="all-MiniLM-L6-v2", device="cpu")
    observations = []
    for case in cases():
        project_root = root / case.case_id
        writer = ProjectMemory(
            base_dir=project_root,
            project_id=case.case_id,
            session_id="write",
            embedder=embedder,
            enable_semantic_graph=False,
        )
        try:
            old_native_id = writer.store_temporal_episode(
                case.old_text,
                topic_key=case.topic_key,
                action="set",
                metadata={"evidence_id": case.old_id},
                importance=1.0,
                bypass_filter=True,
            )
            current_native_id = writer.store_temporal_episode(
                case.current_text,
                topic_key=case.topic_key,
                action=case.current_action,
                metadata={"evidence_id": case.current_id},
                importance=1.0,
                bypass_filter=True,
            )
            writer_chroma_count = writer.chromadb.count() if writer.chromadb else 0
        finally:
            writer.close()

        events = []
        telemetry = Telemetry()
        telemetry.add_sink(events.append)
        reader = ProjectMemory(
            base_dir=project_root,
            project_id=case.case_id,
            session_id="cold",
            embedder=embedder,
            telemetry=telemetry,
            enable_semantic_graph=False,
        )
        try:
            current_hits = reader.search_episodes(case.current_query, n=5)
            current_search = next(
                event.data for event in reversed(events) if event.event_type == "search_completed"
            )
            historical_hits = reader.search_episodes(
                case.historical_query, n=5, include_historical=True
            )
            historical_search = next(
                event.data for event in reversed(events) if event.event_type == "search_completed"
            )
            current_prompt = reader.build_prompt(
                case.current_query,
                query=case.current_query,
                reserve_output_tokens=64,
                return_trace=True,
            )
            historical_prompt = reader.build_prompt(
                case.historical_query,
                query=case.historical_query,
                reserve_output_tokens=64,
                return_trace=True,
            )
            current_ids = _ids(current_hits)
            historical_ids = _ids(historical_hits)
            current_prompt_ids = _prompt_ids(current_prompt)
            historical_prompt_ids = _prompt_ids(historical_prompt)
            current_item = next(
                (
                    item
                    for item in current_hits
                    if item.metadata.get("evidence_id") == case.current_id
                ),
                None,
            )
            historical_old = next(
                (
                    item
                    for item in historical_hits
                    if item.metadata.get("evidence_id") == case.old_id
                ),
                None,
            )
            observations.append(
                {
                    "case_id": case.case_id,
                    "native_ids_persisted": bool(old_native_id and current_native_id),
                    "writer_chroma_count": writer_chroma_count,
                    "cold_chroma_count": reader.chromadb.count() if reader.chromadb else 0,
                    "current_ranked_ids": current_ids,
                    "historical_ranked_ids": historical_ids,
                    "current_prompt_ids": current_prompt_ids,
                    "historical_prompt_ids": historical_prompt_ids,
                    "current_vector_used": bool(current_search["used_vector_search"]),
                    "historical_vector_used": bool(historical_search["used_vector_search"]),
                    "current_filtered_count": current_search["temporal_filtered_count"],
                    "current_only_active": current_ids == (case.current_id,),
                    "historical_has_both": case.old_id in historical_ids
                    and case.current_id in historical_ids,
                    "current_prompt_only_active": current_prompt_ids == (case.current_id,),
                    "historical_prompt_has_old": case.old_id in historical_prompt_ids,
                    "current_metadata_active": bool(
                        current_item and current_item.metadata.get("temporal_status") == "active"
                    ),
                    "old_metadata_superseded": bool(
                        historical_old
                        and historical_old.metadata.get("temporal_status") == "superseded"
                    ),
                    "old_superseded_by_current": bool(
                        historical_old
                        and historical_old.metadata.get("superseded_by") == current_native_id
                    ),
                    "current_prompt_tokens": current_prompt.get("prompt_tokens"),
                    "historical_prompt_tokens": historical_prompt.get("prompt_tokens"),
                    "memory_starved": bool(
                        current_prompt["budget_diagnostics"]["memory_starved"]
                        or historical_prompt["budget_diagnostics"]["memory_starved"]
                    ),
                }
            )
        finally:
            reader.close()
    checks = (
        "native_ids_persisted",
        "current_vector_used",
        "historical_vector_used",
        "current_only_active",
        "historical_has_both",
        "current_prompt_only_active",
        "historical_prompt_has_old",
        "current_metadata_active",
        "old_metadata_superseded",
        "old_superseded_by_current",
    )
    return {
        "schema_version": 1,
        "profile": PROFILE,
        "profile_version": PROFILE_VERSION,
        "suite_digest": suite_digest(),
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "finished_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "embedder_label": "sentence-transformers/all-MiniLM-L6-v2",
        "embedding_dimension": 384,
        "offline_cached_model": True,
        "case_count": len(observations),
        "prior_unstarted_dependency_attempts": 1,
        "cold_reopen_pass_count": sum(
            all(item[check] for check in checks) and not item["memory_starved"]
            for item in observations
        ),
        "vector_current_pass_count": sum(
            item["current_vector_used"] and item["current_only_active"] for item in observations
        ),
        "historical_pass_count": sum(
            item["historical_vector_used"] and item["historical_has_both"] for item in observations
        ),
        "metadata_pass_count": sum(
            item["current_metadata_active"]
            and item["old_metadata_superseded"]
            and item["old_superseded_by_current"]
            for item in observations
        ),
        "observations": observations,
        "privacy": {
            "raw_queries_retained": False,
            "raw_memories_retained": False,
            "host_paths_retained": False,
        },
        "interpretation_limit": "Three synthetic timelines using one cached embedding model on CPU; not a scale or general retrieval claim.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    args = parser.parse_args(argv)
    target = prepare_new_artifact_path(args.artifact)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    with tempfile.TemporaryDirectory(prefix="engram-temporal-vector-cold-") as tmp:
        body = run(Path(tmp))
    target.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps({k: v for k, v in body.items() if k != "observations"}, indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

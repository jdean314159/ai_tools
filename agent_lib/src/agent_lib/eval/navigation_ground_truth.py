from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .navigation_contracts import NavigationConfigurationError


LEAD_QUESTION = (
    "Within production Python under rag_lib/src, identify (1) where the persistent Chroma client "
    "and collections are initialized, (2) every direct Chroma collection mutation call, such as "
    "upsert or delete, and (3) each RAGPipeline call site that invokes those storage mutations. "
    "Exclude tests, documentation, abstract interfaces, retrieval-only operations, and references "
    "that merely mention Chroma."
)


@dataclass(frozen=True)
class GroundTruthRegion:
    id: str
    path: str
    start_line: int
    end_line: int
    classification: str
    required_answer_terms: tuple[str, ...] = ()
    symbol: str = ""


def load_ground_truth(path: str | Path) -> tuple[str, list[GroundTruthRegion]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    regions = [
        GroundTruthRegion(
            id=str(item["id"]),
            path=str(item["path"]),
            start_line=int(item["start_line"]),
            end_line=int(item["end_line"]),
            classification=str(item["classification"]),
            required_answer_terms=tuple(
                str(term) for term in item.get("required_answer_terms") or []
            ),
            symbol=str(item.get("symbol") or ""),
        )
        for item in payload["regions"]
    ]
    if not regions or len({region.id for region in regions}) != len(regions):
        raise NavigationConfigurationError(
            "Ground truth requires a non-empty set of unique region IDs"
        )
    for region in regions:
        region_path = Path(region.path)
        if (
            region_path.is_absolute()
            or ".." in region_path.parts
            or region.start_line < 1
            or region.end_line < region.start_line
        ):
            raise NavigationConfigurationError(
                f"Invalid ground-truth region bounds or path: {region.id}"
            )
        if not region.classification.strip() or not region.required_answer_terms:
            raise NavigationConfigurationError(
                f"Ground-truth region {region.id} requires classification and required_answer_terms"
            )
    return str(payload.get("question") or LEAD_QUESTION), regions


def validate_ground_truth_snapshot(
    path: str | Path,
    manifest: dict[str, Any],
    root: str | Path,
) -> None:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, dict):
        raise NavigationConfigurationError("Ground truth requires snapshot metadata")
    expected_git_sha = snapshot.get("git_sha")
    if expected_git_sha != manifest.get("git_sha"):
        raise NavigationConfigurationError(
            f"Ground-truth Git SHA mismatch: key={expected_git_sha}, repo={manifest.get('git_sha')}"
        )
    expected_sources = snapshot.get("source_sha256")
    if not isinstance(expected_sources, dict) or not expected_sources:
        raise NavigationConfigurationError("Ground truth requires snapshot.source_sha256")
    manifest_sources = {
        item["path"]: item["sha256"] for item in manifest.get("allowed_sources") or []
    }
    for source_path, expected_hash in expected_sources.items():
        actual_hash = manifest_sources.get(str(source_path))
        if actual_hash != expected_hash:
            raise NavigationConfigurationError(
                f"Ground-truth source hash mismatch for {source_path}: key={expected_hash}, repo={actual_hash}"
            )
    resolved_root = Path(root).resolve(strict=True)
    for item in payload.get("regions") or []:
        source_path = str(item.get("path") or "")
        if source_path not in expected_sources:
            raise NavigationConfigurationError(
                f"Ground-truth region uses an unpinned source: {source_path}"
            )
        start_line = int(item["start_line"])
        end_line = int(item["end_line"])
        lines = (resolved_root / source_path).read_text(encoding="utf-8").splitlines()
        region_text = "\n".join(lines[start_line - 1 : end_line])
        anchors = item.get("anchors")
        if not isinstance(anchors, list) or not anchors:
            raise NavigationConfigurationError(
                f"Ground-truth region {item.get('id')} requires anchors"
            )
        for anchor in anchors:
            if str(anchor) not in region_text:
                raise NavigationConfigurationError(
                    f"Ground-truth anchor missing in {item.get('id')}: {anchor!r}"
                )

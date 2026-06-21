#!/usr/bin/env python3
"""Validate deterministic decision-history metadata in ADR front matter."""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


ROOT = Path(__file__).resolve().parents[1]
FRONT_MATTER_BOUNDARY = "---"
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s{0,3}(```|~~~)")
IDENTIFIER = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
ADR_ID = r"^ADR-[0-9]{3}$"


class EarlierSupport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    basis: str = Field(min_length=1)
    evidence: list[str]


class HypothesisRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(pattern=IDENTIFIER)
    application_scope: str = Field(pattern=IDENTIFIER)
    resolution_status: Literal[
        "supported",
        "qualified",
        "contested",
        "resolved_against",
        "unresolved",
        "historical",
    ]
    mechanism_status: Literal[
        "operational",
        "not_demonstrated",
        "not_applicable",
    ]
    mechanism_evidence: list[str]
    earlier_support: EarlierSupport
    resolution_evidence: list[str]
    superseded_by: str | None = Field(default=None, pattern=ADR_ID)
    current_guidance: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evidence_requirements(self) -> "HypothesisRecord":
        if self.mechanism_status == "operational" and not self.mechanism_evidence:
            raise ValueError("operational mechanisms require mechanism_evidence")
        if (
            self.mechanism_status in {"not_demonstrated", "not_applicable"}
            and self.mechanism_evidence
        ):
            raise ValueError(
                f"{self.mechanism_status} mechanisms require empty "
                "mechanism_evidence"
            )
        if (
            self.resolution_status == "resolved_against"
            and not self.resolution_evidence
        ):
            raise ValueError("resolved_against requires resolution_evidence")
        return self


class DecisionHistory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    decision_history_version: Literal[1]
    hypotheses: list[HypothesisRecord] = Field(min_length=1)


def extract_front_matter(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONT_MATTER_BOUNDARY:
        return None
    try:
        closing = next(
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == FRONT_MATTER_BOUNDARY
        )
    except StopIteration as exc:
        raise ValueError("front matter has no closing boundary") from exc
    payload = yaml.safe_load("\n".join(lines[1:closing]))
    if not isinstance(payload, dict):
        raise ValueError("front matter must be a YAML mapping")
    if "decision_history_version" not in payload:
        return None
    return payload


def github_heading_slug(heading: str) -> str:
    """Generate the repository-pinned GitHub-style heading slug subset."""
    lowered = heading.strip().lower()
    without_punctuation = re.sub(r"[^\w\s-]", "", lowered)
    return re.sub(r"\s", "-", without_punctuation)


def markdown_heading_slugs(path: Path) -> set[str]:
    counts: dict[str, int] = defaultdict(int)
    slugs: set[str] = set()
    in_fence = False
    fence_marker = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        fence = FENCE.match(line)
        if fence:
            marker = fence.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue
        match = HEADING.match(line)
        if not match:
            continue
        base = github_heading_slug(match.group(1))
        occurrence = counts[base]
        counts[base] += 1
        slugs.add(base if occurrence == 0 else f"{base}-{occurrence}")
    return slugs


def resolve_reference(reference: str, *, source: Path) -> list[str]:
    errors: list[str] = []
    if not reference or reference.startswith(("/", "http://", "https://")):
        return [f"{source}: reference must be a repository-relative path: {reference!r}"]
    path_text, separator, fragment = reference.partition("#")
    if not path_text:
        return [f"{source}: reference must include a file path: {reference!r}"]
    resolved = (ROOT / path_text).resolve()
    if not resolved.is_relative_to(ROOT):
        return [f"{source}: reference escapes repository: {reference!r}"]
    if not resolved.is_file():
        return [f"{source}: missing evidence reference: {reference!r}"]
    if separator:
        if not fragment:
            errors.append(f"{source}: empty heading fragment: {reference!r}")
        elif resolved.suffix.casefold() != ".md":
            errors.append(
                f"{source}: heading fragment requires Markdown: {reference!r}"
            )
        elif fragment not in markdown_heading_slugs(resolved):
            errors.append(f"{source}: unresolved heading fragment: {reference!r}")
    return errors


def record_references(record: HypothesisRecord) -> list[str]:
    return [
        *record.mechanism_evidence,
        *record.earlier_support.evidence,
        *record.resolution_evidence,
    ]


def adr_ids(paths: list[Path]) -> set[str]:
    ids = set()
    for path in paths:
        match = re.match(r"(ADR-[0-9]{3})-", path.name)
        if match:
            ids.add(match.group(1))
    return ids


def validate_paths(paths: list[Path]) -> tuple[int, int, list[str]]:
    failures: list[str] = []
    parsed: list[tuple[Path, DecisionHistory]] = []
    known_adr_ids = adr_ids(paths)
    for path in paths:
        try:
            payload = extract_front_matter(path)
            if payload is None:
                continue
            history = DecisionHistory.model_validate(payload)
        except Exception as exc:
            failures.append(f"{path.relative_to(ROOT)}: invalid metadata: {exc}")
            continue
        parsed.append((path, history))
        for record in history.hypotheses:
            if record.superseded_by and record.superseded_by not in known_adr_ids:
                failures.append(
                    f"{path.relative_to(ROOT)}: unknown superseded_by ADR "
                    f"{record.superseded_by}"
                )
            for reference in record_references(record):
                failures.extend(
                    resolve_reference(reference, source=path.relative_to(ROOT))
                )

    by_key: dict[tuple[str, str], list[tuple[Path, str]]] = defaultdict(list)
    for path, history in parsed:
        for record in history.hypotheses:
            by_key[(record.id, record.application_scope)].append(
                (path, record.resolution_status)
            )
    for key, entries in by_key.items():
        statuses = {status for _, status in entries}
        if len(statuses) > 1:
            locations = ", ".join(
                f"{path.relative_to(ROOT)}={status}" for path, status in entries
            )
            failures.append(
                f"conflicting exact-key decisions for {key[0]}/{key[1]}: "
                f"{locations}"
            )
    record_count = sum(len(history.hypotheses) for _, history in parsed)
    return len(parsed), record_count, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate ADR decision-history metadata"
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="ADR Markdown paths; defaults to adr/ADR-*.md",
    )
    args = parser.parse_args(argv)
    paths = (
        [
            (ROOT / path).resolve() if not path.is_absolute() else path
            for path in args.paths
        ]
        if args.paths
        else sorted((ROOT / "adr").glob("ADR-*.md"))
    )
    document_count, record_count, failures = validate_paths(paths)
    if failures:
        print("Decision-history validation FAILED:\n")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(
        "Decision-history validation passed "
        f"({document_count} documents, {record_count} records)."
    )
    print("References resolve; evidentiary claims were not content-verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

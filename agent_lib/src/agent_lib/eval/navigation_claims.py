"""Structured, evidence-linked claims for repository-navigation evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


NAVIGATION_CLAIMS_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "path": {"type": "string", "minLength": 1},
            "symbol": {"type": "string", "minLength": 1},
            "operation": {"type": "string", "minLength": 1},
            "classification": {"type": "string", "minLength": 1},
            "evidence": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "path": {"type": "string", "minLength": 1},
                        "start_line": {"type": "integer", "minimum": 1},
                        "end_line": {"type": "integer", "minimum": 1},
                    },
                    "required": ["path", "start_line", "end_line"],
                },
            },
        },
        "required": ["path", "symbol", "operation", "classification", "evidence"],
    },
}


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    path: str
    start_line: int
    end_line: int

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceRef":
        return cls(
            path=str(value.get("path") or ""),
            start_line=int(value.get("start_line") or 0),
            end_line=int(value.get("end_line") or 0),
        )


@dataclass(frozen=True, slots=True)
class NavigationClaim:
    path: str
    symbol: str
    operation: str
    classification: str
    evidence: tuple[EvidenceRef, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "NavigationClaim":
        raw_evidence = value.get("evidence")
        if not isinstance(raw_evidence, list):
            raw_evidence = []
        return cls(
            path=str(value.get("path") or ""),
            symbol=str(value.get("symbol") or ""),
            operation=str(value.get("operation") or ""),
            classification=str(value.get("classification") or ""),
            evidence=tuple(
                EvidenceRef.from_mapping(item)
                for item in raw_evidence
                if isinstance(item, Mapping)
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "symbol": self.symbol,
            "operation": self.operation,
            "classification": self.classification,
            "evidence": [
                {
                    "path": item.path,
                    "start_line": item.start_line,
                    "end_line": item.end_line,
                }
                for item in self.evidence
            ],
        }


@dataclass(frozen=True, slots=True)
class ClaimValidation:
    matched_region_ids: tuple[str, ...]
    missing_region_ids: tuple[str, ...]
    unsupported_claims: tuple[dict[str, Any], ...]
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.missing_region_ids and not self.unsupported_claims and not self.errors


def validate_navigation_claims(
    claims: Sequence[NavigationClaim],
    *,
    telemetry_calls: Sequence[Mapping[str, Any]],
    regions: Sequence[object],
) -> ClaimValidation:
    """Validate claims against observed evidence and claim-local expectations."""

    observed: dict[str, set[int]] = {}
    for call in telemetry_calls:
        if not bool(call.get("success")):
            continue
        for item in call.get("evidence") or []:
            if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
                continue
            observed.setdefault(str(item["path"]), set()).update(
                int(line) for line in item.get("lines") or [] if isinstance(line, int)
            )

    errors: list[str] = []
    unsupported: list[dict[str, Any]] = []
    matched: set[str] = set()
    for index, claim in enumerate(claims, start=1):
        prefix = f"claim {index}"
        if not claim.path or not claim.symbol or not claim.operation or not claim.classification:
            errors.append(f"{prefix} has an empty required field")
            continue
        if not claim.evidence:
            errors.append(f"{prefix} has no evidence references")
            continue
        claim_lines: set[int] = set()
        refs_valid = True
        for ref in claim.evidence:
            if ref.path != claim.path or ref.start_line < 1 or ref.end_line < ref.start_line:
                errors.append(f"{prefix} has an invalid evidence reference")
                refs_valid = False
                continue
            referenced = set(range(ref.start_line, ref.end_line + 1))
            if not referenced.issubset(observed.get(ref.path, set())):
                errors.append(f"{prefix} references unobserved evidence")
                refs_valid = False
            claim_lines.update(referenced)
        if not refs_valid:
            continue

        candidates = []
        for region in regions:
            region_lines = set(
                range(
                    int(getattr(region, "start_line")),
                    int(getattr(region, "end_line")) + 1,
                )
            )
            if (
                claim.path == str(getattr(region, "path"))
                and claim.symbol == str(getattr(region, "symbol", "") or "")
                and claim_lines.intersection(region_lines)
                and _terms_are_claim_local(
                    claim, getattr(region, "required_answer_terms", ())
                )
            ):
                candidates.append(str(getattr(region, "id")))
        if len(candidates) != 1:
            unsupported.append(claim.as_dict())
            continue
        region_id = candidates[0]
        if region_id in matched:
            errors.append(f"{prefix} duplicates region {region_id}")
            continue
        matched.add(region_id)

    expected = {str(getattr(region, "id")) for region in regions}
    return ClaimValidation(
        matched_region_ids=tuple(sorted(matched)),
        missing_region_ids=tuple(sorted(expected - matched)),
        unsupported_claims=tuple(unsupported),
        errors=tuple(errors),
    )


def _terms_are_claim_local(claim: NavigationClaim, terms: Sequence[str]) -> bool:
    haystack = " ".join(
        (claim.path, claim.symbol, claim.operation, claim.classification)
    ).lower()
    return all(str(term).lower() in haystack for term in terms)

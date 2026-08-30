"""Trust policy primitives for persistent memory boundaries."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Mapping


class TrustLevel(IntEnum):
    """Ordered confidence assigned by the application, never inferred by Engram."""

    UNTRUSTED = 0
    LOW = 1
    VERIFIED = 2
    TRUSTED = 3

    @classmethod
    def parse(cls, value: Any, *, default: "TrustLevel | None" = None) -> "TrustLevel":
        fallback = cls.UNTRUSTED if default is None else cls(default)
        if isinstance(value, cls):
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            try:
                return cls(value)
            except ValueError:
                return fallback
        name = str(value or "").strip().upper()
        return cls.__members__.get(name, fallback)


@dataclass(frozen=True)
class TrustDecision:
    action: str
    reasons: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return self.action == "accept"


@dataclass(frozen=True)
class MemoryTrustPolicy:
    """Explicit ingestion and recall policy.

    Applications assign trust; Engram only validates and enforces it. When a
    policy is configured, missing trust and tenant metadata fail closed.
    """

    tenant_id: str
    min_ingest_trust: TrustLevel = TrustLevel.VERIFIED
    min_recall_trust: TrustLevel = TrustLevel.VERIFIED
    allowed_sources: frozenset[str] = frozenset()
    allowed_writers: frozenset[str] = frozenset()
    tenant_aliases: frozenset[str] = frozenset()
    ingestion_violation: str = "reject"

    def __post_init__(self) -> None:
        if not str(self.tenant_id).strip():
            raise ValueError("tenant_id must be non-empty")
        if self.ingestion_violation not in {"reject", "quarantine"}:
            raise ValueError("ingestion_violation must be 'reject' or 'quarantine'")
        if any(not isinstance(alias, str) or not alias.strip() or alias != alias.strip()
               for alias in self.tenant_aliases):
            raise ValueError("tenant_aliases must contain non-empty normalized strings")
        if self.tenant_id in self.tenant_aliases:
            raise ValueError("tenant_aliases must not repeat tenant_id")

    def normalize_metadata(self, metadata: Mapping[str, Any] | None) -> dict[str, Any]:
        normalized = dict(metadata or {})
        normalized["trust"] = TrustLevel.parse(normalized.get("trust")).name.lower()
        for key in ("tenant", "source", "writer"):
            if key in normalized:
                normalized[key] = str(normalized[key]).strip()
        return normalized

    def ingestion_decision(self, metadata: Mapping[str, Any] | None) -> TrustDecision:
        meta = self.normalize_metadata(metadata)
        reasons = self._boundary_reasons(meta, self.min_ingest_trust)
        return TrustDecision(self.ingestion_violation if reasons else "accept", tuple(reasons))

    def recall_decision(self, metadata: Mapping[str, Any] | None) -> TrustDecision:
        meta = self.normalize_metadata(metadata)
        reasons = self._boundary_reasons(meta, self.min_recall_trust)
        if meta.get("quarantined"):
            reasons.append("quarantined")
        return TrustDecision("filter" if reasons else "accept", tuple(reasons))

    def _boundary_reasons(self, meta: Mapping[str, Any], minimum: TrustLevel) -> list[str]:
        reasons: list[str] = []
        authorized_tenants = {self.tenant_id, *self.tenant_aliases}
        if meta.get("tenant") not in authorized_tenants:
            reasons.append("tenant_mismatch")
        if TrustLevel.parse(meta.get("trust")) < minimum:
            reasons.append("trust_below_minimum")
        if self.allowed_sources and meta.get("source") not in self.allowed_sources:
            reasons.append("source_not_allowed")
        if self.allowed_writers and meta.get("writer") not in self.allowed_writers:
            reasons.append("writer_not_allowed")
        return reasons


__all__ = ["MemoryTrustPolicy", "TrustDecision", "TrustLevel"]

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


def capability_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def capability_to_row(value: Any) -> dict[str, Any]:
    payload = capability_to_dict(value)
    return {
        "kind": payload.get("kind", ""),
        "provider": payload.get("provider", ""),
        "component": payload.get("component", ""),
        "version": payload.get("version", ""),
        "summary": payload.get("summary", ""),
        "features": ", ".join(payload.get("features", ()) or ()),
        "input_types": ", ".join(payload.get("input_types", ()) or ()),
        "output_types": ", ".join(payload.get("output_types", ()) or ()),
        "metadata": payload.get("metadata", {}) or {},
    }

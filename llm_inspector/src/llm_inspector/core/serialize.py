from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from typing import Any


def to_dict(obj: Any) -> Any:
    """Dataclass-safe conversion to plain Python objects with stable inspector serialization."""
    if is_dataclass(obj):
        data = {f.name: getattr(obj, f.name) for f in fields(obj)}
        if {"event_type", "source_package", "source_component", "payload"}.issubset(data):
            data.pop("event_id", None)
            data.pop("span_id", None)
            data.pop("parent_span_id", None)
            if not data.get("tags"):
                data.pop("tags", None)
        if "inference_optimizations" in data and not data["inference_optimizations"]:
            data.pop("inference_optimizations", None)
        return {k: to_dict(v) for k, v in data.items()}
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_dict(v) for v in obj]
    return obj


def to_json(obj: Any, *, indent: int = 2, sort_keys: bool = True) -> str:
    return json.dumps(to_dict(obj), indent=indent, sort_keys=sort_keys, ensure_ascii=False)

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Dict

from llm_inspector.inspectors.bundle import CompareBundle


def _to_plain(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    return obj


def bundle_to_dict(bundle: CompareBundle) -> Dict[str, Any]:
    return _to_plain(bundle)


def bundle_to_json(bundle: CompareBundle, *, indent: int = 2, sort_keys: bool = True) -> str:
    return json.dumps(bundle_to_dict(bundle), indent=indent, sort_keys=sort_keys, ensure_ascii=False)
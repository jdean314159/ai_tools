from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Dict

from llm_inspector.inspectors.diff import DiffReport


def _to_plain(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    return obj


def diff_to_dict(diff: DiffReport) -> Dict[str, Any]:
    return _to_plain(diff)


def diff_to_json(diff: DiffReport, *, indent: int = 2, sort_keys: bool = True) -> str:
    return json.dumps(diff_to_dict(diff), indent=indent, sort_keys=sort_keys, ensure_ascii=False)

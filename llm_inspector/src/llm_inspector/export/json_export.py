from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Dict

from llm_inspector.inspectors import ComparisonReport


def _to_plain(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    return obj


def report_to_dict(report: ComparisonReport) -> Dict[str, Any]:
    return _to_plain(report)


def report_to_json(report: ComparisonReport, *, indent: int = 2, sort_keys: bool = True) -> str:
    return json.dumps(report_to_dict(report), indent=indent, sort_keys=sort_keys, ensure_ascii=False)

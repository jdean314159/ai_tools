from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import List

from llm_inspector.inspectors.context_inspector import ComparisonReport, NamedTrace
from llm_inspector.inspectors.diff import DiffReport, diff_traces


@dataclass(frozen=True)
class CompareBundle:
    """A compare result plus all pairwise diffs for UI rendering and regression."""
    report: ComparisonReport
    diffs: List[DiffReport] = field(default_factory=list)


def build_bundle(report: ComparisonReport) -> CompareBundle:
    named: List[NamedTrace] = report.traces
    diffs: List[DiffReport] = []

    for i, j in combinations(range(len(named)), 2):
        a = named[i]
        b = named[j]
        diffs.append(diff_traces(a.trace, b.trace, name_a=a.name, name_b=b.name))

    return CompareBundle(report=report, diffs=diffs)
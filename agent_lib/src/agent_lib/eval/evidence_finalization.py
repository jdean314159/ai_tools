"""Task-agnostic evidence compaction for constrained agent finalization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import re
from typing import Any


_READ_LINE = re.compile(r"^(\d+): ?(.*)$")
_GREP_LINE = re.compile(r"^(.+?):(\d+): ?(.*)$")


@dataclass(frozen=True, slots=True)
class EvidenceLedger:
    """Losslessly deduplicated successful evidence visible to the agent."""

    text: str
    line_atoms: int
    path_atoms: int
    source_paths: tuple[str, ...]


def build_evidence_ledger(steps: Sequence[object]) -> EvidenceLedger:
    """Build a deterministic ledger without task-specific relevance selection."""

    source_lines: dict[tuple[str, int], str] = {}
    paths: set[str] = set()
    residual_results: set[tuple[str, str, str]] = set()

    for step in steps:
        action = _field(step, "action")
        if _field(action, "kind") != "tool":
            continue
        call = _field(action, "tool_call")
        observation = _field(step, "observation")
        result = _field(observation, "tool_result")
        if (
            call is None
            or observation is None
            or result is None
            or not bool(_field(result, "success"))
        ):
            continue
        tool = str(_field(call, "name") or "")
        arguments = _mapping(_field(call, "arguments"))
        meta = _mapping(_field(result, "meta")) or _mapping(_field(observation, "meta"))
        output = str(_field(observation, "text") or "")

        evidence_atoms = _declared_atoms(meta)
        paths.update(path for path, _ in evidence_atoms)
        paths.update(str(path) for path in meta.get("paths") or [] if isinstance(path, str))

        parsed: dict[tuple[str, int], str] = {}
        if tool == "read_file":
            path = str(arguments.get("path") or "")
            for raw_line in output.splitlines():
                match = _READ_LINE.match(raw_line)
                if match and path:
                    parsed[(path, int(match.group(1)))] = match.group(2)
        elif tool == "grep":
            for raw_line in output.splitlines():
                match = _GREP_LINE.match(raw_line)
                if match:
                    parsed[(match.group(1), int(match.group(2)))] = match.group(3)

        for atom in evidence_atoms:
            if atom[1] is not None and atom in parsed:
                source_lines.setdefault((atom[0], int(atom[1])), parsed[atom])

        # NAV's known tools are represented by source lines or paths. Preserve
        # successful unstructured results for future tools rather than silently
        # dropping evidence the ledger cannot parse.
        if tool not in {"read_file", "grep", "list_files"} and output.strip():
            residual_results.add(
                (tool, json.dumps(arguments, sort_keys=True, default=str), output.strip())
            )

    sections: list[str] = []
    by_path: dict[str, list[tuple[int, str]]] = {}
    for (path, line), text in source_lines.items():
        by_path.setdefault(path, []).append((line, text))
    for path in sorted(by_path):
        rendered = "\n".join(f"{line}: {text}" for line, text in sorted(by_path[path]))
        sections.append(f"### {path}\n{rendered}")

    path_only = sorted(paths - set(by_path))
    if path_only:
        sections.append("### Observed paths\n" + "\n".join(path_only))
    for tool, arguments, output in sorted(residual_results):
        sections.append(f"### {tool} {arguments}\n{output}")

    return EvidenceLedger(
        text="\n\n".join(sections),
        line_atoms=len(source_lines),
        path_atoms=len(path_only),
        source_paths=tuple(sorted(paths)),
    )


def _declared_atoms(meta: Mapping[str, Any]) -> set[tuple[str, int | None]]:
    atoms: set[tuple[str, int | None]] = set()
    evidence = meta.get("evidence")
    if isinstance(evidence, list):
        for item in evidence:
            if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
                continue
            path = str(item["path"])
            lines = item.get("lines")
            if isinstance(lines, list) and lines:
                atoms.update((path, int(line)) for line in lines if isinstance(line, int))
            else:
                atoms.add((path, None))
    return atoms


def _field(value: object, name: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}

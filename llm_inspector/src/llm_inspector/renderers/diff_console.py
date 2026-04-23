from __future__ import annotations
from llm_inspector.inspectors.diff import DiffReport
from typing import List

def render_diff(report: DiffReport) -> str:
    lines: List[str] = []
    lines.append(f"Diff: {report.name_a} -> {report.name_b}")
    lines.append("")

    # Flags (only if changed)
    flag_lines = [f"- {k}: {va} -> {vb}" for k, (va, vb) in report.flags.items() if va != vb]
    if flag_lines:
        lines.append("Flags:")
        lines.extend(flag_lines)
        lines.append("")

    # Tokens by origin (only if changed)
    token_lines = [
        f"- {td.origin}: {td.used_a} -> {td.used_b}"
        for td in report.token_deltas
        if td.used_a != td.used_b
    ]
    if token_lines:
        lines.append("Token usage by origin:")
        lines.extend(token_lines)
        lines.append("")

    # Sections (only changed)
    lines.append("Sections:")
    for sd in report.section_deltas:
        if sd.change == "unchanged":
            continue
        if sd.change == "added":
            lines.append(f"+ [{sd.origin}] {sd.title} (tokens={sd.tokens_b})")
        elif sd.change == "removed":
            lines.append(f"- [{sd.origin}] {sd.title} (tokens={sd.tokens_a})")
        else:
            lines.append(f"~ [{sd.origin}] {sd.title} (tokens={sd.tokens_a} -> {sd.tokens_b})")
            if sd.text_a and sd.text_b and sd.text_a != sd.text_b:
                lines.append(f"  - a: {sd.text_a}")
                lines.append(f"  - b: {sd.text_b}")
    lines.append("")

    # Evidence
    if report.evidence_deltas:
        lines.append("Evidence:")
        for ed in report.evidence_deltas:
            prefix = "+" if ed.change == "added" else "-"
            lines.append(f"{prefix} [{ed.source}] {ed.snippet}")
        lines.append("")

    return "\n".join(lines)
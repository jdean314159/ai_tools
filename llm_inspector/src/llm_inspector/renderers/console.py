from __future__ import annotations

from typing import List

from llm_inspector.inspectors import ComparisonReport
from llm_inspector.renderers.origins import console_prefix, label


def render_comparison(report: ComparisonReport) -> str:
    lines: List[str] = []
    lines.append(f"Query: {report.query}")
    lines.append("")

    for nt in report.traces:
        t = nt.trace
        lines.append(f"=== {nt.name} ===")
        acc = t.context.token_accounting
        if acc.target_tokens is not None:
            lines.append(f"Target tokens: {acc.target_tokens}")
        if acc.total_tokens is not None:
            lines.append(f"Total tokens: {acc.total_tokens}")
        if acc.truncated:
            lines.append("Truncated: yes")
        if acc.compressed:
            lines.append("Compressed: yes")

        lines.append("Sections:")
        for s in t.context.sections:
            tok = s.tokens if s.tokens is not None else "-"
            prefix = console_prefix(s.origin)
            lines.append(f"  {prefix} {s.title} (tokens={tok})")

        # Token usage by origin — only non-zero entries
        if acc.per_origin_used:
            lines.append("Token usage by origin:")
            for origin, used in acc.per_origin_used.items():
                if used:
                    lbl = label(origin)
                    prefix = console_prefix(origin)
                    lines.append(f"  {prefix} {lbl}: {used} tokens")

        if t.context.evidence:
            lines.append("Evidence:")
            for e in t.context.evidence:
                score = e.score if e.score is not None else "-"
                prefix = console_prefix(e.source)
                lines.append(f"  {prefix} score={score} {e.meta}")
        if t.context.evidence_flows:
            lines.append("Evidence flow:")
            for flow in t.context.evidence_flows:
                score = flow.score if flow.score is not None else "-"
                prefix = console_prefix(flow.source)
                if flow.excluded:
                    lines.append(
                        f"  {prefix} excluded reason={flow.exclusion_reason or '-'} "
                        f"score={score} before={flow.before_text!r}"
                    )
                else:
                    delta = (
                        repr(flow.after_text)
                        if flow.before_text == flow.after_text
                        else f"{flow.before_text!r} -> {flow.after_text!r}"
                    )
                    xforms = ",".join(flow.transformations) if flow.transformations else "-"
                    lines.append(
                        f"  {prefix} stage={flow.stage} score={score} "
                        f"xforms={xforms} flow={delta}"
                    )
        lines.append("")

    return "\n".join(lines)


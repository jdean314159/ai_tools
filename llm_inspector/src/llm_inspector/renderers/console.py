from __future__ import annotations

from typing import List

from llm_inspector.inspectors import ComparisonReport


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
            lines.append(f"- [{s.origin}] {s.title} (tokens={tok})")

        if t.context.evidence:
            lines.append("Evidence:")
            for e in t.context.evidence:
                score = e.score if e.score is not None else "-"
                lines.append(f"- [{e.source}] score={score} meta={e.meta}")
        if t.context.evidence_flows:
            lines.append("Evidence flow:")
            for flow in t.context.evidence_flows:
                score = flow.score if flow.score is not None else "-"
                if flow.excluded:
                    lines.append(
                        f"- [{flow.source}] excluded reason={flow.exclusion_reason or '-'} score={score} before={flow.before_text!r}"
                    )
                else:
                    delta = repr(flow.after_text) if flow.before_text == flow.after_text else f"{flow.before_text!r} -> {flow.after_text!r}"
                    prov = flow.provenance or {}
                    stage = flow.stage
                    xforms = ",".join(flow.transformations) if flow.transformations else "-"
                    lines.append(
                        f"- [{flow.source}] stage={stage} score={score} xforms={xforms} flow={delta} provenance={prov}"
                    )
        lines.append("")

    return "\n".join(lines)

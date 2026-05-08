from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

from llm_inspector_ui.state.models import RunArtifact
from llm_inspector_ui.utils.teaching_text import (
    describe_compare_group_for_beginners,
    describe_compare_group_for_teaching,
    describe_run_for_beginners,
    describe_run_for_teaching,
    explain_agent_tab,
    explain_agent_tab_for_beginners,
    explain_evidence_tab,
    explain_evidence_tab_for_beginners,
    explain_prompt_tab,
    explain_prompt_tab_for_beginners,
    explain_retrieval_tab,
    explain_retrieval_tab_for_beginners,
    explain_token_tab_for_beginners,
)
from llm_inspector_ui.utils.trace_access import (
    get_agent_events,
    get_agent_execution_rows,
    get_agent_execution_summary,
    get_agent_summary,
    get_evidence,
    get_final_prompt,
    get_retrieval_events,
    get_retrieval_summary,
    get_token_accounting,
)


def _group_runs_by_turn(runs: Iterable[RunArtifact]) -> list[tuple[str, list[RunArtifact]]]:
    grouped: dict[str, list[RunArtifact]] = defaultdict(list)
    for run in runs:
        grouped[run.turn_id].append(run)

    ordered: list[tuple[str, list[RunArtifact]]] = []
    for turn_id, turn_runs in grouped.items():
        ordered.append(
            (
                turn_id,
                sorted(turn_runs, key=lambda r: (r.created_at, r.augmenter_id)),
            )
        )

    ordered.sort(key=lambda item: item[1][0].created_at, reverse=True)
    return ordered


def render_compare_panel(
    runs: list[RunArtifact],
    inspector_service: Any | None = None,
    *,
    beginner_mode: bool = False,
) -> None:
    import streamlit as st

    compare_groups = [
        (turn_id, group)
        for turn_id, group in _group_runs_by_turn(runs)
        if len(group) > 1 or any(run.mode == "compare" for run in group)
    ]

    st.subheader("Compare")
    if not compare_groups:
        st.caption("No compare runs yet.")
        return

    local_beginner_mode = st.toggle(
        "Beginner explanations",
        value=beginner_mode,
        help="Adds plain-language guidance for reading prompts, evidence, retrieval, and agent traces.",
        key="compare_beginner_mode_toggle",
    )

    group_labels = []
    for turn_id, group in compare_groups:
        ts = group[0].created_at.isoformat(timespec="seconds")
        augmenters = ", ".join(f"{run.augmenter_id}:{run.status}" for run in group)
        group_labels.append(f"{ts} | {augmenters} | {turn_id[:8]}")

    selected_label = st.selectbox("Compare group", options=group_labels, index=0)
    selected_index = group_labels.index(selected_label)
    _, selected_group = compare_groups[selected_index]

    st.markdown("**User input**")
    st.write(selected_group[0].user_text)

    expander_title = "How to read this comparison"
    with st.expander(expander_title, expanded=True):
        lessons = (
            describe_compare_group_for_beginners(selected_group)
            if local_beginner_mode
            else describe_compare_group_for_teaching(selected_group)
        )
        for lesson in lessons:
            st.write(f"- {lesson}")

    summary_rows = []
    for run in selected_group:
        token_acc = get_token_accounting(run.trace)
        summary_rows.append(
            {
                "augmenter": run.augmenter_id,
                "status": run.status,
                "engine": run.engine_id,
                "model": run.model_id or "",
                "error": run.error or "",
                "total_tokens": token_acc.get("total_tokens"),
                "compressed": token_acc.get("compressed"),
                "truncated": token_acc.get("truncated"),
            }
        )
    st.dataframe(summary_rows, use_container_width=True)
    if local_beginner_mode:
        st.caption(
            "Read the table left to right: which branch ran successfully, how many tokens it used, and whether compression or truncation changed what the model saw."
        )

    usable_runs = [run for run in selected_group if run.status == "ok" and run.trace]

    if inspector_service is not None and len(usable_runs) >= 1:
        bundle = inspector_service.bundle(
            [(run.augmenter_id, run.trace) for run in usable_runs],
            query=selected_group[0].user_text,
        )
        st.download_button(
            "Download compare bundle JSON",
            data=json.dumps(bundle, indent=2, ensure_ascii=False),
            file_name=f"compare_bundle_{selected_group[0].turn_id[:8]}.json",
            mime="application/json",
            use_container_width=True,
        )

    col_count = max(1, len(selected_group))
    columns = st.columns(col_count)

    for col, run in zip(columns, selected_group):
        with col:
            st.markdown(f"### {run.augmenter_id}")
            st.caption(f"status={run.status}")
            st.info(describe_run_for_beginners(run) if local_beginner_mode else describe_run_for_teaching(run))

            if run.status == "skipped":
                st.warning(run.error or "Branch was skipped.")
                continue

            if run.error:
                st.error(run.error)
                continue

            tabs = st.tabs(["Response", "Prompt", "Token accounting", "Evidence", "Retrieval", "Agent"])

            with tabs[0]:
                if local_beginner_mode:
                    st.caption("Start here. Decide whether this answer is actually better before you inspect the internal details.")
                st.write(run.response_text)

            with tabs[1]:
                st.caption(explain_prompt_tab_for_beginners(run.trace) if local_beginner_mode else explain_prompt_tab(run.trace))
                st.code(get_final_prompt(run.trace, fallback=run.prompt or ""), language="markdown")

            with tabs[2]:
                st.caption(
                    explain_token_tab_for_beginners(run.trace)
                    if local_beginner_mode
                    else "Use token accounting to judge whether the added context justified its cost. Higher token use is not automatically better."
                )
                st.json(get_token_accounting(run.trace))

            with tabs[3]:
                st.caption(explain_evidence_tab_for_beginners(run.trace) if local_beginner_mode else explain_evidence_tab(run.trace))
                evidence = get_evidence(run.trace)
                if not evidence:
                    st.caption("No evidence.")
                else:
                    for item in evidence:
                        source = item.get("source", "")
                        st.markdown(f"**{source}**")
                        st.write(item.get("text", ""))
                        if item.get("score") is not None:
                            st.caption(f"score={item.get('score')}")

            with tabs[4]:
                st.caption(explain_retrieval_tab_for_beginners(run.trace) if local_beginner_mode else explain_retrieval_tab(run.trace))
                summary = get_retrieval_summary(run.trace)
                events = get_retrieval_events(run.trace)
                if summary:
                    st.json(summary)
                if events:
                    st.dataframe(events, use_container_width=True)
                elif not summary:
                    st.caption("No retrieval diagnostics.")

            with tabs[5]:
                st.caption(explain_agent_tab_for_beginners(run.trace) if local_beginner_mode else explain_agent_tab(run.trace))
                summary = get_agent_summary(run.trace)
                exec_summary = get_agent_execution_summary(run.trace)
                rows = get_agent_execution_rows(run.trace)
                events = get_agent_events(run.trace)
                if summary:
                    st.json(summary)
                if rows:
                    st.markdown("**Execution status**")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Blocked", int(exec_summary.get("blocked_count", 0)))
                    c2.metric("Degraded", int(exec_summary.get("degraded_count", 0)))
                    c3.metric("Approval", int(exec_summary.get("approval_count", 0)))
                    st.dataframe(rows, use_container_width=True)
                if events:
                    st.dataframe(events, use_container_width=True)
                elif not summary and not rows:
                    st.caption("No agent diagnostics.")

    if len(usable_runs) == 2 and inspector_service is not None:
        left, right = usable_runs
        diff = inspector_service.diff(
            left.trace,
            right.trace,
            name_a=left.augmenter_id,
            name_b=right.augmenter_id,
        )

        st.markdown("### Diff")
        if local_beginner_mode:
            st.caption(
                "Use the diff to answer one practical question: what changed between the two branches that could explain the difference in answer quality?"
            )

        flags = diff.get("flags", {})
        if flags:
            st.markdown("**Flags**")
            st.json(flags)

        changed_sections = [
            row for row in diff.get("section_deltas", [])
            if row.get("change") != "unchanged"
        ]
        if changed_sections:
            st.markdown("**Section deltas**")
            st.dataframe(changed_sections, use_container_width=True)

        evidence_deltas = diff.get("evidence_deltas", [])
        if evidence_deltas:
            st.markdown("**Evidence deltas**")
            st.dataframe(evidence_deltas, use_container_width=True)

        token_deltas = diff.get("token_deltas", [])
        if token_deltas:
            st.markdown("**Token deltas**")
            st.dataframe(token_deltas, use_container_width=True)

        if not changed_sections and not evidence_deltas and not token_deltas:
            st.caption("No differences reported by llm_inspector diff.")

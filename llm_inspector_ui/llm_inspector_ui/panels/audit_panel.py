"""Audit panel for llm_inspector_ui.

Three sections:
  Run Audit  — config form + run button, shows AuditReport summary
  Findings   — filterable table with per-finding remediate buttons
  History    — lightweight log of past audit runs this session

Design principles:
  - Read-only by default (dry_run=True)
  - Mutation requires explicit per-finding confirmation
  - Bulk apply requires a global checkbox acknowledgement
  - Degrades gracefully for engram_lite (no audit_memory)

Author: Jeffrey Dean
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Helpers shared with synthesis_panel
# ---------------------------------------------------------------------------

def _get_pm(base_dir: Path, project_id: str, project_type: str = "programming_assistant"):
    try:
        from engram.project_memory import ProjectMemory
        try:
            from engram import ProjectType
        except Exception:
            from engram.project_memory import ProjectType
        return ProjectMemory(
            project_id=project_id,
            project_type=ProjectType(project_type),
            base_dir=base_dir,
            llm_engine=None,
        )
    except Exception:
        return None


def _has_audit(pm) -> bool:
    return (
        pm is not None
        and hasattr(pm, "audit_memory")
        and hasattr(pm, "audit_remediate")
    )


def _fmt_ts(ts: Optional[float]) -> str:
    if ts is None:
        return "—"
    try:
        return datetime.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "—"


# Severity badge colours for st.markdown badges
_SEVERITY_COLORS = {
    "error": "#dc3545",
    "warn":  "#fd7e14",
    "info":  "#0dcaf0",
}
_SEVERITY_LABELS = {
    "error": "🔴 ERROR",
    "warn":  "🟠 WARN",
    "info":  "🔵 INFO",
}

_CHECK_DESCRIPTIONS = {
    "orphan_synthesis":     "Rules whose supporting episodes have been deleted.",
    "contradicting_facts":  "Fact pairs with conflicting claims about the same subject.",
    "stale_facts":          "Facts that haven't been re-validated within the stale window.",
    "low_confidence_rules": "Synthesis rules below the confidence threshold.",
    "dangling_relations":   "Graph edges whose subject or object no longer exists.",
    "near_duplicate_rules": "Near-identical synthesis rules that should be merged.",
}


# ---------------------------------------------------------------------------
# Main panel renderer
# ---------------------------------------------------------------------------

def render_audit_panel(
    augmenter_service: Any,
    *,
    beginner_mode: bool = False,
) -> None:
    import streamlit as st

    st.header("Memory Audit & Lint")

    # --- Availability check ------------------------------------------
    try:
        import engram  # noqa: F401
    except ImportError:
        st.warning("Engram is not installed.")
        return

    base_dir = Path(augmenter_service.engram_base_dir)
    project_id = augmenter_service.engram_project_id
    project_type = getattr(augmenter_service, "engram_project_type", "programming_assistant")

    pm = _get_pm(base_dir, project_id, project_type)
    if pm is None:
        st.error("Could not initialise ProjectMemory. Check base directory.")
        return

    if not _has_audit(pm):
        st.info(
            "Audit is not available for this augmenter. "
            "Switch to the **engram** augmenter (not engram_lite)."
        )
        pm.close()
        return

    if beginner_mode:
        st.caption(
            "The **memory audit** scans for problems in stored memory: "
            "orphaned rules, conflicting facts, stale data, weak rules, and broken graph edges. "
            "All checks are read-only — nothing changes until you explicitly approve a fix."
        )

    # Session-level audit report storage
    if "audit_report" not in st.session_state:
        st.session_state.audit_report = None
    if "audit_history" not in st.session_state:
        st.session_state.audit_history = []

    run_tab, findings_tab, history_tab = st.tabs(["Run Audit", "Findings", "History"])

    with run_tab:
        _render_run_tab(pm, project_id, beginner_mode)

    with findings_tab:
        _render_findings_tab(pm, project_id)

    with history_tab:
        _render_history_tab()

    pm.close()


# ---------------------------------------------------------------------------
# Tab renderers
# ---------------------------------------------------------------------------

def _render_run_tab(pm, project_id: str, beginner_mode: bool) -> None:
    import streamlit as st

    st.subheader("Configure & Run")

    # Check selection
    all_checks = list(_CHECK_DESCRIPTIONS.keys())
    selected_checks = st.multiselect(
        "Checks to run",
        options=all_checks,
        default=all_checks,
        format_func=lambda c: c.replace("_", " ").title(),
        key="audit_selected_checks",
    )
    if beginner_mode and selected_checks:
        for check in selected_checks:
            st.caption(f"**{check}** — {_CHECK_DESCRIPTIONS.get(check, '')}")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        stale_days = st.number_input(
            "Stale fact threshold (days)",
            min_value=30, max_value=730, value=180, step=30,
            help="Facts older than this with no re-validation are flagged.",
            key="audit_stale_days",
        )
        confidence_threshold = st.slider(
            "Low-confidence rule threshold",
            min_value=0.0, max_value=1.0, value=0.65, step=0.05,
            help="Rules below this confidence are flagged.",
            key="audit_confidence_threshold",
        )
    with col2:
        contradiction_overlap = st.slider(
            "Contradiction overlap threshold",
            min_value=0.5, max_value=1.0, value=0.70, step=0.05,
            help="Jaccard similarity floor for contradiction detection.",
            key="audit_contradiction_overlap",
        )
        duplicate_overlap = st.slider(
            "Near-duplicate overlap threshold",
            min_value=0.5, max_value=1.0, value=0.85, step=0.05,
            help="Jaccard similarity floor for near-duplicate rule detection.",
            key="audit_duplicate_overlap",
        )

    if not selected_checks:
        st.warning("Select at least one check.")
        return

    if st.button("▶ Run Audit", type="primary", key="audit_run_btn"):
        with st.spinner("Auditing memory…"):
            try:
                report = pm.audit_memory(
                    checks=selected_checks,
                    stale_days=int(stale_days),
                    confidence_threshold=float(confidence_threshold),
                    contradiction_overlap=float(contradiction_overlap),
                    duplicate_overlap=float(duplicate_overlap),
                )
            except Exception as exc:
                st.error(f"Audit failed: {exc}")
                return

        st.session_state.audit_report = report
        # Append summary to history
        st.session_state.audit_history.append({
            "timestamp": _fmt_ts(report.audit_timestamp),
            "checks": ", ".join(report.checks_run),
            "error": report.summary().get("error", 0),
            "warn":  report.summary().get("warn", 0),
            "info":  report.summary().get("info", 0),
            "elapsed": f"{report.elapsed_seconds:.2f}s",
        })

        # Summary metrics
        s = report.summary()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total findings", report.count)
        c2.metric("🔴 Errors", s["error"])
        c3.metric("🟠 Warnings", s["warn"])
        c4.metric("🔵 Info", s["info"])

        if report.count == 0:
            st.success("No issues found — memory is clean.")
        else:
            st.info("Switch to the **Findings** tab to review and act on results.")

        if report.checks_skipped:
            with st.expander("Skipped checks"):
                for name, reason in report.checks_skipped.items():
                    st.caption(f"- **{name}**: {reason}")

        with st.expander("Markdown report"):
            st.markdown(report.to_markdown())


def _render_findings_tab(pm, project_id: str) -> None:
    import streamlit as st

    report = st.session_state.get("audit_report")
    if report is None:
        st.info("Run an audit first (use the **Run Audit** tab).")
        return

    if report.count == 0:
        st.success("No findings — memory is clean.")
        return

    # Filter controls
    col1, col2 = st.columns(2)
    with col1:
        severity_filter = st.multiselect(
            "Filter by severity",
            options=["error", "warn", "info"],
            default=["error", "warn", "info"],
            format_func=lambda s: _SEVERITY_LABELS.get(s, s),
            key="audit_severity_filter",
        )
    with col2:
        check_filter = st.multiselect(
            "Filter by check",
            options=list({f.check_name for f in report.findings}),
            default=list({f.check_name for f in report.findings}),
            format_func=lambda c: c.replace("_", " ").title(),
            key="audit_check_filter",
        )

    visible = [
        f for f in report.sorted_findings()
        if f.severity in severity_filter and f.check_name in check_filter
    ]

    if not visible:
        st.info("No findings match the current filter.")
        return

    st.caption(f"Showing {len(visible)} / {report.count} finding(s)")

    # --- Bulk apply section ---
    st.divider()
    bulk_enabled = st.checkbox(
        "⚠ Enable bulk remediation (applies suggested action to ALL visible findings)",
        key="audit_bulk_enable",
    )
    if bulk_enabled:
        if st.button(
            f"Apply suggested actions to {len(visible)} finding(s)",
            type="primary",
            key="audit_bulk_apply",
        ):
            actions = [(f.record_id, f.suggested_action.split()[0].lower())
                       for f in visible if f.suggested_action]
            try:
                result = pm.audit_remediate(report, actions=actions, dry_run=False)
                applied = len(result.get("applied", []))
                errors = len(result.get("errors", []))
                st.success(f"Applied {applied} action(s).")
                if errors:
                    st.warning(f"{errors} error(s) — see expander.")
                with st.expander("Remediation result"):
                    st.json(result)
                # Clear report so user re-runs audit to see updated state
                st.session_state.audit_report = None
                st.rerun()
            except Exception as exc:
                st.error(f"Bulk remediation failed: {exc}")
    st.divider()

    # --- Per-finding rows ---
    for finding in visible:
        sev_label = _SEVERITY_LABELS.get(finding.severity, finding.severity.upper())
        sev_color = _SEVERITY_COLORS.get(finding.severity, "#adb5bd")
        with st.container():
            col_sev, col_info, col_action = st.columns([1, 5, 2])
            with col_sev:
                st.markdown(
                    f'<span style="color:{sev_color};font-weight:bold">{sev_label}</span>',
                    unsafe_allow_html=True,
                )
            with col_info:
                st.markdown(
                    f"**[{finding.check_name.replace('_',' ').title()}]** "
                    f"`{finding.record_type}` · `{finding.record_id[:20]}…`  \n"
                    f"{finding.details}"
                )
                if finding.suggested_action:
                    st.caption(f"Suggested: _{finding.suggested_action}_")
            with col_action:
                if finding.suggested_action:
                    action_word = finding.suggested_action.split()[0].lower()
                    btn_key = f"audit_apply_{finding.record_id}_{action_word}"
                    if st.button(
                        action_word.replace("_", " ").title(),
                        key=btn_key,
                        help=f"Apply '{action_word}' to {finding.record_id}",
                    ):
                        try:
                            result = pm.audit_remediate(
                                report,
                                actions=[(finding.record_id, action_word)],
                                dry_run=False,
                            )
                            applied = result.get("applied", [])
                            if applied:
                                st.success(f"Applied: {action_word}")
                            else:
                                skipped = result.get("skipped", [])
                                st.warning(
                                    f"Skipped: {skipped[0].get('reason','unknown') if skipped else 'no result'}"
                                )
                        except Exception as exc:
                            st.error(f"Failed: {exc}")
            st.divider()


def _render_history_tab() -> None:
    import streamlit as st

    history = st.session_state.get("audit_history", [])
    if not history:
        st.info("No audit runs this session.")
        return

    import pandas as pd
    df = pd.DataFrame(history)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f"{len(history)} audit run(s) this session.")

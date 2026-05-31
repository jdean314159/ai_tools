from __future__ import annotations

import json

from diagnostics_agent import (
    ChatTurn,
    CollectionReadError,
    DiagnosticsOrchestrator,
    FollowupChat,
    LogInterpreter,
    LogTriage,
    journalctl_collector,
    list_local_models,
    make_staging_sandbox,
)
from diagnostics_agent.models import ModelDiscoveryError, detect_available_vram_bytes


_TIME_WINDOWS = {
    "Last 1h": "-1h",
    "Last 6h": "-6h",
    "Last 24h": "-24h",
    "Last 3 days": "-3d",
}
_PRIORITIES = ("emergency", "alert", "critical", "error", "warning")


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="Diagnostics Agent", layout="wide")
    st.title("Diagnostics Agent")

    vram = detect_available_vram_bytes()
    model_error = None
    models = []
    try:
        models = list_local_models(available_vram_bytes=vram)
    except ModelDiscoveryError as exc:
        model_error = str(exc)

    if model_error:
        st.error(f"Ollama unreachable: {model_error}")
    if not models:
        st.warning("No local Ollama models found.")

    selected_model = None
    if models:
        model_labels = {f"{model.name}  ({model.fit})": model.name for model in models}
        selected_label = st.selectbox("Model", list(model_labels))
        selected_model = model_labels[selected_label]
    else:
        st.selectbox("Model", ["No local models found"], disabled=True)

    priority = st.selectbox("Priority", _PRIORITIES, index=_PRIORITIES.index("warning"))
    window_label = st.selectbox("Time window", list(_TIME_WINDOWS), index=2)
    run_clicked = st.button("Run diagnostics", disabled=not selected_model)

    if run_clicked and selected_model is not None:
        with st.spinner("Running diagnostics..."):
            try:
                from llm_engines.backends.ollama import OllamaEngine

                collector = journalctl_collector(priority=priority, since=_TIME_WINDOWS[window_label])
                engine = OllamaEngine(model=selected_model)
                result = DiagnosticsOrchestrator(
                    collector=collector,
                    triage=LogTriage(),
                    interpreter=LogInterpreter(engine),
                    sandbox=make_staging_sandbox(),
                ).run()
                st.session_state["diagnostics_result"] = result
                st.session_state["diagnostics_error"] = None
                st.session_state["followup_history"] = []
                st.session_state["followup_error"] = None
            except Exception as exc:
                st.session_state["diagnostics_result"] = None
                st.session_state["diagnostics_error"] = exc
                st.session_state["followup_history"] = []

    error = st.session_state.get("diagnostics_error")
    if error is not None:
        _render_error(st, error)

    result = st.session_state.get("diagnostics_result")
    if result is not None:
        _render_result(st, result)
        _render_followup_chat(st, result, selected_model)


def _render_error(st, error: Exception) -> None:
    if isinstance(error, CollectionReadError):
        st.error(str(error))
    else:
        st.error(str(error))
        if "journalctl" in str(error).lower() or "collection command failed" in str(error).lower():
            st.info(
                "Ensure your user can read the journal, for example via the "
                "systemd-journal group. Do not run this app as root."
            )


def _render_result(st, result) -> None:
    st.subheader("Run Metadata")
    col1, col2, col3 = st.columns(3)
    col1.metric("Bytes collected", result.collected.byte_count)
    col2.metric("Lines parsed", result.summary.parsed_lines)
    col3.metric("Unparsed", result.summary.unparsed_lines)
    st.code(" ".join(result.collected.command), language="bash")

    sandbox = result.sandbox_result
    if sandbox is not None:
        st.caption(
            f"Sandbox read: exit={sandbox.exit_code}, timed_out={sandbox.timed_out}, "
            f"truncated={sandbox.truncated}"
        )

    st.subheader("Severity Counts")
    severity_cols = st.columns(max(1, len(result.summary.severity_counts)))
    for column, (severity, count) in zip(severity_cols, result.summary.severity_counts.items()):
        column.metric(severity.name, count)

    st.subheader("Findings")
    if result.summary.findings:
        for finding in result.summary.findings:
            st.markdown(
                f"**{finding.rule_name}** | {finding.category} | "
                f"{finding.severity.name} | count {finding.count}"
            )
            st.code(finding.template)
    else:
        st.caption("No rule-based findings.")

    st.subheader("Top Clusters")
    for cluster in result.summary.top_clusters:
        st.markdown(f"**{cluster.count}x** | {cluster.severity.name}")
        st.code(cluster.template)
        for example in cluster.examples[:2]:
            st.caption(example[:500])

    st.subheader("Interpretation")
    if result.interpretation is None:
        st.warning(f"Interpretation failed: {result.interpretation_error}")
    else:
        interp = result.interpretation
        risk_col1, risk_col2 = st.columns(2)
        risk_col1.metric("Security risk", interp.security_risk)
        risk_col2.metric("Operational risk", interp.operational_risk)
        st.write(interp.summary)
        st.markdown("**Prioritized concerns**")
        for concern in interp.prioritized_concerns:
            st.markdown(f"- **{concern.severity}** `{concern.finding_ref}`: {concern.rationale}")
        st.markdown("**Recommended checks**")
        for check in interp.recommended_checks:
            st.markdown(f"- {check}")

    audit_json = json.dumps(result.audit, indent=2)
    with st.expander("Raw audit"):
        st.json(result.audit)
        st.download_button(
            "Download audit JSON",
            data=audit_json,
            file_name="diagnostics-audit.json",
            mime="application/json",
        )


def _render_followup_chat(st, result, selected_model: str | None) -> None:
    st.subheader("Follow-up Q&A")
    history = st.session_state.setdefault("followup_history", [])
    for turn in history:
        with st.chat_message(turn.role):
            st.write(turn.content)

    question = st.chat_input("Ask about these results", disabled=selected_model is None)
    if question and selected_model is not None:
        try:
            from llm_engines.backends.ollama import OllamaEngine

            with st.spinner("Answering..."):
                reply = FollowupChat(OllamaEngine(model=selected_model)).answer(
                    result,
                    question,
                    tuple(history),
                )
            history.extend([ChatTurn("user", question), ChatTurn("assistant", reply)])
            st.session_state["followup_history"] = history
            st.session_state["followup_error"] = None
            st.rerun()
        except Exception as exc:
            st.session_state["followup_error"] = str(exc)

    followup_error = st.session_state.get("followup_error")
    if followup_error:
        st.error(followup_error)


if __name__ == "__main__":
    main()

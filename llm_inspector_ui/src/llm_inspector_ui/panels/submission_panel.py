from __future__ import annotations

import streamlit as st

from llm_inspector_ui.services.orchestrator import RunPlan


def render_run_readiness_banner(readiness) -> None:
    if readiness.can_run:
        st.caption(f"Run readiness: {readiness.message}")
        return

    if readiness.severity == "warning":
        st.warning(readiness.message)
    else:
        st.error(readiness.message)

    with st.expander("Run readiness details", expanded=False):
        st.json(readiness.details or {})


def render_submission_readiness_banner(submission_readiness: dict[str, object]) -> None:
    message = str(submission_readiness.get("message", ""))
    severity = submission_readiness.get("severity", "ok")

    if severity == "ok":
        st.caption(f"Submission readiness: {message}")
    elif severity == "warning":
        st.warning(message)
    else:
        st.error(message)

    branch_readiness = submission_readiness.get("branch_readiness", [])
    if branch_readiness:
        with st.expander("Branch readiness", expanded=False):
            st.json(
                [
                    {
                        "augmenter_id": item.augmenter_id,
                        "can_run": item.can_run,
                        "severity": item.severity,
                        "message": item.message,
                        "details": item.details,
                    }
                    for item in branch_readiness
                ]
            )


def submit_input(controls: dict[str, object]):
    submission_readiness = controls.get("submission_readiness", {})
    disabled = not bool(submission_readiness.get("can_submit", False))

    prompt = st.chat_input("Send a message", disabled=disabled)
    if not prompt:
        return

    submission_readiness = controls.get("submission_readiness", {})
    if not submission_readiness.get("can_submit", False):
        st.error(str(submission_readiness.get("message", "Submission is blocked.")))
        return

    plan = RunPlan(
        session_id=st.session_state.current_session_id,
        user_text=prompt,
        engine_id=controls["engine_id"],
        model_id=controls["model_id"],
        augmenter_ids=list(controls["augmenter_ids"]),
        engine_config=dict(controls["engine_config"]),
        engine_settings=dict(controls["engine_settings"]),
        max_prompt_tokens=controls["max_prompt_tokens"],
        reserve_output_tokens=controls["reserve_output_tokens"],
        augmenter_options=dict(controls["augmenter_options"]),
    )

    with st.spinner("Running..."):
        st.session_state.orchestrator.run(plan)
    st.rerun()

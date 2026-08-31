from __future__ import annotations

from typing import Any


def render_artifact_replay_panel(
    inspector_service: Any,
    *,
    beginner_mode: bool = False,
) -> None:
    """Render read-only inspection replay for one shared run-artifact JSON file."""
    import streamlit as st

    st.subheader("Artifact replay")
    st.caption(
        "Load a shared run artifact for offline inspection. "
        "Nothing is executed or imported into session history."
    )
    if beginner_mode:
        st.info(
            "Replay here means parsing the saved record and rebuilding its inspection summary. "
            "It does not rerun the model, tools, or original experiment."
        )
    uploaded = st.file_uploader(
        "Run artifact JSON", type=["json"], accept_multiple_files=False,
        key="shared_artifact_replay_upload",
    )
    if uploaded is None:
        return
    try:
        inspection = inspector_service.replay_artifact_json(uploaded.getvalue())
    except ValueError as exc:
        st.error(str(exc))
        return

    common = dict(inspection.get("common") or {})
    st.success("Artifact parsed and validated.")
    st.json({
        "record_id": common.get("record_id"),
        "kind": common.get("kind"),
        "profile": common.get("profile"),
        "lifecycle": common.get("lifecycle"),
        "body_support": inspection.get("body_support"),
    })
    notices = list(inspection.get("notices") or [])
    for notice in notices:
        st.warning(str(notice))
    st.markdown("**Body summary**")
    body_summary = inspection.get("body_summary")
    if body_summary is None:
        st.caption("This body/profile version is unsupported; only common envelope facts are shown.")
    else:
        st.json(body_summary)
    with st.expander("Common artifact facts", expanded=False):
        st.json(common)

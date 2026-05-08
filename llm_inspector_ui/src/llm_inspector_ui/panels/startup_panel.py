from __future__ import annotations

from llm_inspector_ui.interop import describe_ui
from llm_inspector_ui.utils.teaching_text import (
    describe_readiness_steps_for_beginners,
    explain_readiness_for_beginners,
    explain_readiness_for_teaching,
)
from llm_inspector_ui.utils.capability_access import capability_to_dict, capability_to_row


def _agent_execution_capability_rows(descriptors: list[object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in descriptors:
        payload = capability_to_dict(item)
        features = tuple(payload.get("features", ()) or ())
        metadata = payload.get("metadata", {}) or {}
        if not isinstance(metadata, dict):
            metadata = {}
        supports = any(
            key in metadata for key in ("blocked_execution_reporting", "degraded_execution_reporting", "approval_gates")
        ) or any(
            feature in features
            for feature in (
                "blocked_execution_reporting",
                "degraded_execution_reporting",
                "approval_gates",
            )
        )
        if not supports:
            continue
        rows.append({
            "provider": payload.get("provider", ""),
            "component": payload.get("component", ""),
            "blocked_execution_reporting": bool(metadata.get("blocked_execution_reporting", False) or ("blocked_execution_reporting" in features)),
            "degraded_execution_reporting": bool(metadata.get("degraded_execution_reporting", False) or ("degraded_execution_reporting" in features)),
            "approval_gates": bool(metadata.get("approval_gates", False) or ("approval_gates" in features)),
            "summary": payload.get("summary", ""),
        })
    return rows


def render_startup_panel(
    engine_service,
    *,
    selected_engine_id: str,
    selected_engine_config: dict | None = None,
    augmenter_service=None,
    inspector_service=None,
    selected_augmenter_ids: list[str] | None = None,
    augmenter_options: dict | None = None,
    beginner_mode: bool = False,
 ) -> None:
    import streamlit as st

    st.subheader("Startup")

    config = dict(selected_engine_config or {})
    local_beginner_mode = st.toggle(
        "Beginner explanations",
        value=beginner_mode,
        help="Adds plain-language setup guidance and next steps.",
        key="startup_beginner_mode_toggle",
    )
    col_a, col_b = st.columns([1, 1])

    with col_a:
        if st.button("Refresh readiness", use_container_width=True):
            st.rerun()

    with col_b:
        recommended = engine_service.recommend_default_engine(configs={selected_engine_id: config})
        st.caption(f"Recommended default: {recommended}")

    st.markdown("**Current engine config**")
    if config:
        st.json(config)
    else:
        st.caption("No engine config fields are currently set.")

    selected = engine_service.get_engine_health(selected_engine_id, config=config)

    st.markdown("**Selected engine**")
    st.json(
        {
            "engine_id": selected.engine_id,
            "label": selected.label,
            "status": selected.status,
            "exists": selected.exists,
            "reachable": selected.reachable,
            "models_available": selected.models_available,
            "model_count": selected.model_count,
            "message": selected.message,
        }
    )

    if selected.status == "error":
        st.error(selected.message or "Selected engine is not usable.")
    elif selected.status == "warning":
        st.warning(selected.message or "Selected engine is only partially ready.")
    else:
        st.success(selected.message or "Selected engine is ready.")

    if selected.details:
        with st.expander("Health details", expanded=False):
            st.json(selected.details)

    descriptors = [
        describe_ui(),
        engine_service.describe_engine_capability(selected_engine_id, config=config),
    ]
    if inspector_service is not None and hasattr(inspector_service, "describe_component"):
        descriptors.append(inspector_service.describe_component())
    if augmenter_service is not None:
        descriptors.extend(
            augmenter_service.list_augmenter_capabilities(
                list(selected_augmenter_ids or []),
                options_by_id=dict(augmenter_options or {}),
            )
        )

    st.markdown("**Component capabilities**")
    st.dataframe([capability_to_row(item) for item in descriptors], use_container_width=True)

    if local_beginner_mode:
        st.caption(
            "This table shows what each component claims it can do. For beginners, the main question is whether the engine, inspector, and selected augmenters are all visible through the same shared interface."
        )

    with st.expander("Capability metadata", expanded=False):
        st.json([capability_to_dict(item) for item in descriptors])

    execution_rows = _agent_execution_capability_rows(descriptors)
    if execution_rows:
        st.markdown("**Agent execution visibility support**")
        st.dataframe(execution_rows, use_container_width=True)
        if local_beginner_mode:
            st.caption(
                "These rows tell you whether the workbench can show blocked actions, degraded execution, and approval gates. Visibility is not the same as hard runtime isolation, but it is necessary for teaching safe agent behavior."
            )

    st.markdown("**Models visible with current config**")
    try:
        models = engine_service.list_models(selected_engine_id, config=config)
    except Exception as exc:
        models = []
        st.error(f"Model probe failed: {type(exc).__name__}: {exc}")

    if models:
        st.dataframe(
            [
                {
                    "model_id": m.model_id,
                    "label": m.label,
                    "source": m.source,
                    "installed": m.installed,
                    **m.metadata,
                }
                for m in models
            ],
            use_container_width=True,
        )
    else:
        st.caption("No models visible with the current config.")

    st.markdown("**All engines**")
    health_rows = engine_service.engine_health_summary(configs={selected_engine_id: config})
    if health_rows:
        st.dataframe(health_rows, use_container_width=True)
    else:
        st.caption("No engines available.")

    st.markdown("**Readiness guide**")
    st.write(
        explain_readiness_for_beginners(
            status=selected.status,
            exists=selected.exists,
            reachable=selected.reachable,
            models_available=selected.models_available,
        )
        if local_beginner_mode
        else explain_readiness_for_teaching(
            status=selected.status,
            exists=selected.exists,
            reachable=selected.reachable,
            models_available=selected.models_available,
        )
    )

    if local_beginner_mode:
        st.markdown("**Suggested next steps**")
        for step in describe_readiness_steps_for_beginners(
            status=selected.status,
            exists=selected.exists,
            reachable=selected.reachable,
            models_available=selected.models_available,
        ):
            st.write(f"- {step}")

    if not selected.exists:
        st.write("The engine is not registered. Choose another engine or wire the llm_engines registry into the UI.")
    elif selected.reachable is False:
        st.write("The engine is registered but not reachable. Start the backend service or fix its connection settings, then refresh.")
    elif selected.models_available is False:
        st.write("The engine is reachable but has no available models. Use the Models tab to provision or register one.")
    elif selected.status == "ok":
        st.write("The engine is ready for chat and comparison runs.")
    else:
        st.write("The engine is partially configured. Check health details and model availability.")

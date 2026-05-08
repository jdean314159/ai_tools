from __future__ import annotations

import streamlit as st

from llm_inspector_ui.utils.capability_access import capability_to_row


def render_models_panel(engine_service) -> None:
    st.subheader("Models")

    health = engine_service.engine_health_summary()
    if health:
        st.markdown("**Engine summary**")
        st.dataframe(health, use_container_width=True)

    capabilities = [capability_to_row(item) for item in engine_service.list_engine_capabilities()]
    if capabilities:
        st.markdown("**Engine capabilities**")
        st.dataframe(capabilities, use_container_width=True)

    st.markdown("**Search / Provision**")
    search_query = st.text_input("Model search query", value="", key="model_search_query")
    search_source = st.selectbox(
        "Search source",
        options=["any", "huggingface", "local", "ollama", "vllm"],
        index=0,
        key="model_search_source",
    )

    if st.button("Search models", use_container_width=True):
        source = None if search_source == "any" else search_source
        results = engine_service.search_models(search_query, source=source)
        st.session_state.model_search_results = results

    results = st.session_state.get("model_search_results", [])
    if results:
        rows = [
            {
                "model_id": item.model_id,
                "label": item.label,
                "source": item.source,
                "installed": item.installed,
                **item.metadata,
            }
            for item in results
        ]
        st.dataframe(rows, use_container_width=True)

        model_labels = [f"{item.label} [{item.source}]" for item in results]
        selected_label = st.selectbox(
            "Provision target",
            options=model_labels,
            index=0,
            key="provision_model_select",
        )
        selected = results[model_labels.index(selected_label)]

        target_engine_id = st.text_input(
            "Target engine id",
            value="",
            help="Optional. Leave blank if provisioning is source-native.",
            key="provision_target_engine_id",
        )

        if st.button("Provision selected model", use_container_width=True):
            provision = engine_service.provision_model(
                source=selected.source,
                model_id=selected.model_id,
                target_engine_id=target_engine_id or None,
                options={},
            )
            if provision.success:
                st.success(provision.message or f"Provisioned {provision.model_id}")
            else:
                st.error(provision.message or f"Failed to provision {provision.model_id}")
    else:
        st.caption("No search results yet.")

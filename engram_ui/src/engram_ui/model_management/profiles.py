"""Profile editor and page orchestrator.

The profile editor manages failover chains (primary + fallback engines).
``render_model_management()`` is the page entry point called by app.py.

Author: Jeffrey Dean
"""
from __future__ import annotations

import streamlit as st

from engram.engine.model_manager import add_engine_to_profile

from ._shared import _config_path, _load_config, _save_config
from .add_models import _render_hf_search, _render_local_import
from .inventory import (
    _render_hardware,
    _render_registered_engines,
    _render_running_models,
)


# ------------------------------------------------------------------
# Profile editor
# ------------------------------------------------------------------

def _render_profile_editor():
    """Edit failover profiles — primary/fallback model selection."""
    st.subheader("Profile Editor")
    st.caption(
        "Profiles define the engine failover chain. The first engine is **primary**; "
        "subsequent engines are fallbacks tried in order."
    )

    cfg = _load_config()
    profiles = cfg.get("profiles", {})
    engines_cfg = cfg.get("engines", {})
    all_engine_names = sorted(engines_cfg.keys())

    if not profiles:
        st.warning("No profiles found in config. Create one below.")

    # Profile selector
    profile_names = sorted(profiles.keys())
    tab_edit, tab_new = st.tabs(["Edit existing", "Create new"])

    with tab_edit:
        if not profile_names:
            st.info("No profiles to edit.")
            return

        selected = st.selectbox("Profile", profile_names, key="mm_prof_sel")
        prof = profiles.get(selected, {})
        current_engines = list(prof.get("engines", []))

        st.write("**Current engine order** (first = primary):")
        if not current_engines:
            st.write("  (empty)")
        else:
            for idx, eng in enumerate(current_engines):
                ecfg = engines_cfg.get(eng, {})
                etype = ecfg.get("type", "?")
                model = ecfg.get("model", "?")
                role = "Primary" if idx == 0 else f"Fallback {idx}"
                st.write(f"  **{idx+1}. {eng}** ({etype}) — `{model}` [{role}]")

        # Add engine to profile
        st.write("---")
        available = [e for e in all_engine_names if e not in current_engines]
        if available:
            col_add, col_pos, col_btn = st.columns([2, 1, 1])
            with col_add:
                new_eng = st.selectbox("Add engine", available, key="mm_prof_add_eng")
            with col_pos:
                position = st.selectbox("As", ["Primary", "Fallback"], key="mm_prof_add_pos")
            with col_btn:
                st.write("")  # Spacer
                if st.button("Add", key="mm_prof_add_btn"):
                    pos = "prepend" if position == "Primary" else "append"
                    if add_engine_to_profile(selected, new_eng, pos, _config_path()):
                        st.success(f"Added **{new_eng}** as {position.lower()} to **{selected}**.")
                        st.rerun()
                    else:
                        st.warning(f"{new_eng} is already in {selected}.")
        else:
            st.caption("All registered engines are already in this profile.")

        # Remove engine from profile
        if current_engines:
            col_rm, col_rm_btn = st.columns([3, 1])
            with col_rm:
                rm_eng = st.selectbox("Remove engine", current_engines, key="mm_prof_rm_eng")
            with col_rm_btn:
                st.write("")
                if st.button("Remove", key="mm_prof_rm_btn"):
                    cfg = _load_config()
                    eng_list = cfg["profiles"][selected].get("engines", [])
                    if rm_eng in eng_list:
                        eng_list.remove(rm_eng)
                        _save_config(cfg)
                        st.success(f"Removed **{rm_eng}** from **{selected}**.")
                        st.rerun()

        # Cloud failover toggle
        allow_cloud = st.toggle(
            "Allow cloud failover",
            value=bool(prof.get("allow_cloud_failover", False)),
            key="mm_prof_cloud",
            help="If enabled, the router may fail over to cloud engines.",
        )
        if allow_cloud != bool(prof.get("allow_cloud_failover", False)):
            cfg = _load_config()
            cfg["profiles"][selected]["allow_cloud_failover"] = allow_cloud
            _save_config(cfg)

    with tab_new:
        new_name = st.text_input("New profile name", key="mm_prof_new_name",
                                  placeholder="e.g., my_local, fast_cpu")

        # Let user pick engines from the registered list
        if all_engine_names:
            primary = st.selectbox("Primary engine", all_engine_names, key="mm_prof_new_primary")
            fallbacks = st.multiselect(
                "Fallback engines (in order)",
                [e for e in all_engine_names if e != primary],
                key="mm_prof_new_fallbacks",
            )
        else:
            st.warning("No engines registered. Add a model first.")
            primary = None
            fallbacks = []

        if st.button("Create profile", key="mm_prof_new_btn", disabled=not new_name or not primary):
            cfg = _load_config()
            eng_list = [primary] + fallbacks
            cfg.setdefault("profiles", {})[new_name] = {
                "engines": eng_list,
                "allow_cloud_failover": False,
                "max_attempts": 4,
            }
            _save_config(cfg)
            st.success(f"Created profile **{new_name}** with engines: {eng_list}")
            st.rerun()


# ------------------------------------------------------------------
# Page orchestrator (entry point called from app.py)
# ------------------------------------------------------------------

def render_model_management():
    """Render the full model management page."""
    st.header("Models")
    st.caption("Track what is configured, downloaded, running, and selected. This page is organized as an operations console, not just a picker.")

    _render_hardware()
    st.divider()

    _render_running_models()
    st.divider()

    st.subheader("Search & Add Models")
    _render_hf_search()
    st.divider()

    _render_local_import()
    st.divider()

    _render_registered_engines()
    st.divider()

    _render_profile_editor()

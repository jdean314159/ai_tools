"""Read-only inventory views: hardware, running models, registered engines.

These three sections render the current state of the system without
mutating config. They are the "operations console" portion of the page.

Author: Jeffrey Dean
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

from engram.engine.model_manager import (
    SystemInfo,
    score_model_fit as _score_model_fit,
)
from engram_ui.diagnostics_bridge import system_info as shared_system_info

from ._shared import (
    _K_SYSTEM,
    _apply_launch_profile_to_engine,
    _build_engine_inventory,
    _default_resource_profile_name,
    _endpoint_status,
    _engine_resource_advisor,
    _fit_badge_label,
    _friendly_endpoint_error,
    _launch_priority_preference,
    _load_config,
    _maybe_render_model_list,
    _render_resource_advisor_profiles,
    _render_status_badge,
    _render_system_recommendations,
    _render_vllm_launch_guidance,
    _resource_profile_rows,
    _runtime_badge_label,
    _runtime_state_badge,
    _safe_exists,
    _save_config,
    _status_icon,
)


# ------------------------------------------------------------------
# Hardware panel
# ------------------------------------------------------------------

def _render_hardware():
    """Show detected hardware."""
    st.subheader("System Hardware")

    if st.button("Detect hardware", key="mm_detect_hw"):
        with st.spinner("Detecting..."):
            st.session_state[_K_SYSTEM] = shared_system_info()

    sys_info: Optional[SystemInfo] = st.session_state.get(_K_SYSTEM)
    if sys_info is None:
        st.info("Click **Detect hardware** to scan your system.")
        return

    if getattr(sys_info, "warning", None):
        st.warning(sys_info.warning)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("System RAM", f"{sys_info.ram_gb or '?'} GB")
    with col2:
        st.metric("Total VRAM", f"{sys_info.total_vram_gb:.1f} GB")
    with col3:
        st.metric("Accelerator", sys_info.accelerator.upper())

    if sys_info.gpus:
        for g in sys_info.gpus:
            st.caption(f"GPU {g.index}: {g.name} — {g.vram_gb} GB")
    else:
        st.caption("No GPU detected. Models will run on CPU via Ollama.")


# ------------------------------------------------------------------
# Running models panel
# ------------------------------------------------------------------

def _render_running_models():
    """Show live endpoints plus configured engine inventory."""
    st.subheader("Active Runtime Status")

    cfg = _load_config()
    engines_cfg = cfg.get("engines", {}) or {}
    _render_system_recommendations(cfg)
    selected_profile = st.session_state.get("ui_cfg").profile if st.session_state.get("ui_cfg") else "default_local"
    rows = _build_engine_inventory(cfg, selected_profile)

    ollama_urls = sorted({(r["endpoint"] or "").replace("/v1", "").rstrip("/") for r in rows if r["backend"] == "ollama" and r["endpoint"]})
    vllm_urls = sorted({r["endpoint"].rstrip("/") for r in rows if r["backend"] in {"vllm", "openai", "openai-compatible", "openai_compatible"} and r["endpoint"]})
    llama_cpp_urls = sorted({r["endpoint"].rstrip("/") for r in rows if r["backend"] in {"llama_cpp", "llama-cpp", "llamacpp"} and r["endpoint"]})

    live_col, active_col = st.columns([1.3, 1])
    with live_col:
        st.markdown("**Live endpoints**")
        if not ollama_urls and not vllm_urls and not llama_cpp_urls:
            st.caption("No Ollama, vLLM, or llama.cpp endpoints are configured.")

        for url in ollama_urls:
            ok, models, err = _endpoint_status(url, "ollama")
            icon = _status_icon("reachable" if ok else "unreachable")
            st.write(f"{icon} **Ollama** `{url}` — {'reachable' if ok else 'unreachable'}")

            if ok:
                _maybe_render_model_list(models, "ollama")
            else:
                st.caption(_friendly_endpoint_error(url, err))
                with st.expander("Technical details", expanded=False):
                    st.code(err or "No technical details available.", language="text")

        for url in vllm_urls:
            backend_hint = "openai" if "api.openai.com" in url else "vllm"

            ok, models, err = _endpoint_status(url, "vllm")
            icon = _status_icon("reachable" if ok else "unreachable")
            label = "OpenAI" if "api.openai.com" in url else "vLLM"
            st.write(f"{icon} **{label}** `{url}` — {'reachable' if ok else 'unreachable'}")

            if ok:
                _maybe_render_model_list(models, backend_hint)
            else:
                st.caption(_friendly_endpoint_error(url, err))
                with st.expander("Technical details", expanded=False):
                    st.code(err or "No technical details available.", language="text")

        for url in llama_cpp_urls:
            ok, models, err = _endpoint_status(url, "vllm")  # same OpenAI protocol
            icon = _status_icon("reachable" if ok else "unreachable")
            st.write(f"{icon} **llama.cpp** `{url}` — {'reachable' if ok else 'unreachable'}")
            if ok:
                _maybe_render_model_list(models, "vllm")
            else:
                st.caption(_friendly_endpoint_error(url, err))
                with st.expander("Technical details", expanded=False):
                    st.code(err or "No technical details available.", language="text")
    with active_col:
        st.markdown("**Current session binding**")
        selected = [r for r in rows if r["selected"]]

        if not selected:
            st.info("No engine is selected in the active profile.")
        else:
            row = selected[0]
            st.write(f"**Primary: {row['engine_name']}**")
            st.caption(f"backend: {row['backend']} | endpoint: {row['endpoint'] or 'n/a'}")
            st.caption(
                f"served: {'yes' if row['served'] else 'no'} | "
                f"downloaded: {'yes' if row['downloaded'] else ('n/a' if row['downloaded'] is None else 'no')}"
            )
            if row["backend"] in {"vllm", "openai-compatible", "openai_compatible", "llama_cpp", "llama-cpp", "llamacpp"}:
                _render_vllm_launch_guidance(row)

            if len(selected) > 1:
                st.markdown("**Fallback engines**")
                for idx, fb in enumerate(selected[1:], start=1):
                    st.write(f"**Fallback {idx}: {fb['engine_name']}**")
                    st.caption(f"backend: {fb['backend']} | endpoint: {fb['endpoint'] or 'n/a'}")
                    st.caption(
                        f"served: {'yes' if fb['served'] else 'no'} | "
                        f"downloaded: {'yes' if fb['downloaded'] else ('n/a' if fb['downloaded'] is None else 'no')}"
                    )

    st.divider()
    st.subheader("Configured Engines")
    if not rows:
        st.info("No engines registered. Use Search or Import below to add models.")
    else:
        for row in rows:
            with st.expander(f"{row['engine_name']} — {row['backend']} — {row['artifact_family']}", expanded=row['selected']):
                st.write(f"**Model / ref:** `{row['model'] or '(none configured)'}`")
                if row['hf_repo_id']:
                    st.caption(f"HF repo: `{row['hf_repo_id']}`")
                if row['local_model_dir']:
                    exists = _safe_exists(row['local_model_dir'])
                    st.caption(f"Local model dir: `{row['local_model_dir']}` ({'present' if exists else 'missing'})")

                fit = _score_model_fit(
                    model_text=row.get("model", ""),
                    hf_repo_id=row.get("hf_repo_id", ""),
                    local_model_dir=row.get("local_model_dir", ""),
                    backend=row.get("backend", ""),
                    n_gpu_layers=int(row.get("n_gpu_layers") or 0),
                )

                st.caption(f"GPU free: {fit['free_vram_gb']} / {fit['total_vram_gb']} GB")
                if fit["fit"] == "good":
                    st.success("Good fit")
                elif fit["fit"] == "borderline":
                    st.warning("Borderline fit")
                elif fit["fit"] == "blocked_now":
                    st.info("Would fit, but current VRAM is occupied")
                elif fit["fit"] == "better_ollama":
                    st.info("Better candidate for Ollama")
                elif fit["fit"] == "likely_oom":
                    st.error("Likely too large")
                elif fit["fit"] == "remote":
                    st.info("Remote / cloud runtime")

                st.caption(
                    f"{_fit_badge_label(fit['fit'])} | "
                    f"{_runtime_badge_label(fit['runtime'])} | "
                    f"format: {fit['artifact_family'] or 'unknown'}"
                )
                st.caption(fit["rationale"])

                st.caption(_render_status_badge('Selected in profile', row['selected']))
                st.caption(_render_status_badge('Endpoint reachable', row['reachable']))
                st.caption(_render_status_badge('Serving this model', row['served']))
                st.caption(_render_status_badge('Downloaded locally', row['downloaded']))
                st.write(f"**Runtime status:** {_runtime_state_badge(row['runtime_state'])}")
                st.caption(row["runtime_message"])

                engine_resource_advisor = _engine_resource_advisor(engines_cfg.get(row['engine_name'], {}))
                if row['backend'] == 'vllm' and engine_resource_advisor:
                    st.markdown("**Launch profile editor**")
                    profile_options = [item['profile'] for item in _resource_profile_rows(engine_resource_advisor)]
                    saved_profile = str((engines_cfg.get(row['engine_name'], {}) or {}).get('launch_profile') or '')
                    default_profile = saved_profile or _default_resource_profile_name(
                        engine_resource_advisor,
                        preference=_launch_priority_preference(),
                    )
                    if default_profile not in profile_options and profile_options:
                        default_profile = profile_options[0]
                    col_lp, col_btn = st.columns([3, 1])
                    with col_lp:
                        selected_profile = st.selectbox(
                            "Apply launch profile",
                            profile_options,
                            index=profile_options.index(default_profile) if default_profile in profile_options else 0,
                            key=f"mm_existing_launch_profile_{row['engine_name']}",
                            help="Update this engine entry using the shared llm_engines launch-profile settings.",
                        )
                    with col_btn:
                        st.write("")
                        if st.button("Apply", key=f"mm_apply_launch_profile_{row['engine_name']}"):
                            if _apply_launch_profile_to_engine(
                                row['engine_name'],
                                profile_name=selected_profile,
                                resource_advisor=engine_resource_advisor,
                            ):
                                st.success(f"Applied launch profile `{selected_profile}` to `{row['engine_name']}`.")
                                st.rerun()
                    _render_resource_advisor_profiles(engine_resource_advisor)

                if row['endpoint']:
                    st.caption(f"Endpoint: `{row['endpoint']}`")

                if row['served_models']:
                    with st.expander("Discovered served models", expanded=False):
                        for m in row['served_models']:
                            st.write(f"`{m}`")

                if row["backend"] in {"vllm", "openai-compatible", "openai_compatible", "llama_cpp", "llama-cpp", "llamacpp"}:
                    _render_vllm_launch_guidance(row)

                if row['runtime_state'] == "wrong_model":
                    st.warning("The endpoint is reachable, but it is not serving the model Engram expects for this engine.")

                if row['endpoint_error']:
                    st.warning(f"Endpoint status: {row['endpoint_error']}")

    st.divider()
    st.subheader("Downloaded Local Models")
    local_rows = [r for r in rows if r['local_model_dir']]
    if not local_rows:
        st.caption("No local model directories are registered yet.")
    else:
        for row in local_rows:
            exists = _safe_exists(row['local_model_dir'])
            st.write(f"**{row['engine_name']}** — `{row['local_model_dir']}`")
            st.caption(f"format: {row['artifact_family']} | exists: {'yes' if exists else 'no'}")
            if row['hf_repo_id']:
                st.caption(f"HF repo: `{row['hf_repo_id']}`")

            fit = _score_model_fit(
                model_text=row["engine_name"],
                hf_repo_id=row.get("hf_repo_id", ""),
                local_model_dir=row["local_model_dir"],
                backend=row.get("backend", ""),
            )

            st.caption(
                f"{_fit_badge_label(fit['fit'])} | "
                f"{_runtime_badge_label(fit['runtime'])}"
            )
            st.caption(fit["rationale"])


# ------------------------------------------------------------------
# Registered engines panel
# ------------------------------------------------------------------

def _render_registered_engines():
    """Show and manage registered engine entries."""
    st.subheader("Engine Registry")

    cfg = _load_config()
    engines_cfg = cfg.get("engines", {})

    if not engines_cfg:
        st.info("No engines registered. Use Search or Import above to add models.")
        return

    for name, ecfg in sorted(engines_cfg.items()):
        etype = ecfg.get("type", "?")
        model = ecfg.get("model", "?")
        base_url = ecfg.get("base_url", "")
        max_ctx = ecfg.get("max_context", "?")
        num_gpu = ecfg.get("num_gpu")

        detail = f"{etype} · `{model}` · ctx={max_ctx}"
        if num_gpu is not None:
            detail += f" · gpu_layers={num_gpu}"
        if base_url:
            detail += f" · {base_url}"

        col_info, col_del = st.columns([5, 1])
        with col_info:
            st.write(f"**{name}** — {detail}")
        with col_del:
            if st.button("Delete", key=f"mm_eng_del_{name}"):
                cfg = _load_config()
                cfg.get("engines", {}).pop(name, None)
                # Also remove from any profiles
                for pname, pcfg in cfg.get("profiles", {}).items():
                    eng_list = pcfg.get("engines", [])
                    if name in eng_list:
                        eng_list.remove(name)
                _save_config(cfg)
                st.success(f"Deleted engine **{name}**.")
                st.rerun()

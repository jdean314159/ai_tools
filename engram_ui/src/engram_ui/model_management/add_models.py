"""Action flows for adding models: HF search + install + local import.

These sections perform downloads, registrations, and config writes. Each
renderer drives a multi-step interactive flow (search → recommend →
download → register) rather than just displaying state.

Author: Jeffrey Dean
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from engram.engine.model_manager import (
    FormatRecommendation,
    HFModelInfo,
    LocalModelInfo,
    SystemInfo,
    classify_hf_model_format,
    default_local_model_dir,
    download_hf_model,
    download_ollama_model,
    import_gguf_to_ollama,
    recommend_format_for_hf_model,
    register_model_in_config,
    scan_local_model,
    search_hf_models,
    score_model_fit as _score_model_fit,
)
from engram.engine.runtime_status import (
    build_llama_cpp_launch_command,
    build_vllm_launch_command,
)

from ._shared import (
    _K_LOCAL,
    _K_SEARCH,
    _K_SYSTEM,
    _config_path,
    _default_resource_profile_name,
    _fit_badge_label,
    _launch_priority_preference,
    _remember_launch_priority_preference,
    _render_resource_advisor_profiles,
    _resource_profile_engine_extra,
    _resource_profile_rows,
    _runtime_badge_label,
    _vllm_launch_preview_cfg,
)


# ------------------------------------------------------------------
# HuggingFace search panel
# ------------------------------------------------------------------

def _render_hf_search():
    """Search HuggingFace and show recommendations."""
    st.subheader("Search HuggingFace Models")

    col_q, col_n = st.columns([3, 1])
    include_quantized = st.checkbox(
        "Include quantized repos (AWQ/GPTQ/GGUF)",
        value=True,
        key="mm_hf_include_quantized",
        help="Search base repos and common quantized variants instead of filtering to base models only.",
    )
    with col_q:
        query = st.text_input(
            "Search query",
            placeholder="e.g. Qwen2.5 7B, Llama 3, Mistral",
            key="mm_hf_query",
        )
    with col_n:
        limit = st.number_input("Max results", 5, 50, 15, key="mm_hf_limit")

    if st.button("Search", key="mm_hf_search", disabled=not query):
        with st.spinner(f"Searching HuggingFace for '{query}'..."):
            results = search_hf_models(
                query,
                limit=int(limit),
                include_quantized=include_quantized,
                vram_gb=(st.session_state.get(_K_SYSTEM).primary_vram_gb if st.session_state.get(_K_SYSTEM) else None),
            )
            st.session_state[_K_SEARCH] = results
            if not results:
                st.warning("No models found. Try a different query.")

    results: List[HFModelInfo] = st.session_state.get(_K_SEARCH, [])
    if not results:
        return

    sys_info: Optional[SystemInfo] = st.session_state.get(_K_SYSTEM)
    vram = sys_info.primary_vram_gb if sys_info else 0.0

    st.caption(f"Showing {len(results)} results. "
               f"VRAM budget: {vram:.1f} GB" + (" (detect hardware first for recommendations)" if vram == 0 else ""))

    for i, model in enumerate(results):
        with st.expander(
            f"**{model.repo_id}** — {model.size_str()} · "
            f"{model.downloads:,} downloads · "
            f"{'GGUF ' if model.has_gguf else ''}{'safetensors' if model.has_safetensors else ''}",
            expanded=False,
        ):
            repo_id = model.repo_id
            fit = _score_model_fit(
                model_text=repo_id,
                hf_repo_id=repo_id,
                local_model_dir="",
                backend="vllm",
            )

            if fit["fit"] == "likely_oom":
                st.warning("Likely too large for reliable local use on this system.")
            elif fit["fit"] == "better_ollama":
                st.info("This model is likely a better candidate for Ollama than vLLM on this system.")
            elif fit["fit"] == "blocked_now":
                st.info("This model should fit on this machine, but current GPU memory is already occupied.")
            elif fit["fit"] == "borderline":
                st.info("Borderline fit. Conservative context and memory settings may be required.")

            st.caption(
                f"{_fit_badge_label(fit['fit'])} | "
                f"{_runtime_badge_label(fit['runtime'])} | "
                f"format: {fit['artifact_family']}"
            )
            st.caption(fit["rationale"])

            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"**Author:** {model.author}")
                st.write(f"**Pipeline:** {model.pipeline_tag}")
                if model.estimated_params_b:
                    st.write(f"**Parameters:** {model.estimated_params_b:.1f}B")
                    st.write(f"**FP16 size:** ~{model.estimated_size_gb_fp16:.1f} GB")
            with col_b:
                st.write(f"**Downloads:** {model.downloads:,}")
                st.write(f"**Likes:** {model.likes:,}")
                if model.tags:
                    st.write(f"**Tags:** {', '.join(model.tags[:8])}")
                family = classify_hf_model_format(model)
                family_label = {
                    "gguf": "GGUF / Ollama-style",
                    "transformers_quantized": "Transformers quantized (AWQ/GPTQ/EXL2)",
                    "mixed": "Mixed signals (GGUF + Transformers quant)",
                    "base": "Base / generic",
                }.get(family, family)
                st.write(f"**Artifact family:** {family_label}")

            if model.estimated_params_b and vram > 0:
                rec = recommend_format_for_hf_model(model, vram)
                _render_recommendation(rec)
                _render_install_button(model, rec, i)
            elif model.estimated_params_b:
                st.info("Detect hardware to get a format recommendation.")
            else:
                st.warning("Cannot estimate model size from repo name. Check the model card for parameter count.")


def _render_recommendation(rec: FormatRecommendation):
    """Show format recommendation as a colored callout."""
    engine_label = {"vllm": "vLLM", "ollama": "Ollama", "llama_cpp": "llama.cpp"}.get(rec.engine, rec.engine.upper())
    if rec.fits_in_vram:
        st.success(
            f"**Recommended:** {engine_label} with {rec.quantization} "
            f"({rec.estimated_vram_gb:.1f} GB estimated)\n\n"
            f"{rec.reason}"
        )
    elif rec.engine == "llama_cpp":
        st.warning(
            f"**Recommended:** {engine_label} split offload — {rec.quantization} "
            f"({rec.num_gpu_layers} GPU layers, rest on CPU)\n\n"
            f"{rec.reason}\n\n"
            f"Download the GGUF file, then use the **llama.cpp** install option below."
        )
    else:
        st.warning(
            f"**Recommended:** {engine_label} with {rec.quantization} "
            f"(partial offload, {rec.num_gpu_layers} GPU layers)\n\n"
            f"{rec.reason}"
        )

    _render_resource_advisor_profiles(rec.resource_advisor)


def _render_install_button(model: HFModelInfo, rec: FormatRecommendation, idx: int):
    """Download/register button for a search result."""
    col_name, col_btn = st.columns([2, 1])

    # Generate a sensible engine name
    safe_name = re.sub(r"[^a-z0-9_]", "_", model.name.lower())
    if rec.quantization != "fp16":
        safe_name += f"_{rec.quantization.lower()}"

    key_suffix = re.sub(r"[^a-z0-9_]+", "_", model.repo_id.lower())

    with col_name:
        engine_name = st.text_input(
            "Engine name",
            value=safe_name,
            key=f"mm_eng_name_{key_suffix}",
            help="Name used in llm_engines.yaml and profiles. Bound to the selected Hugging Face result, not cached by row position.",
        )

    selected_launch_profile = ""
    selected_launch_extra: Dict[str, Any] = {}
    if rec.engine == "vllm" and rec.resource_advisor:
        profile_options = [row["profile"] for row in _resource_profile_rows(rec.resource_advisor)]
        preference_labels = {
            "balanced": "Balanced",
            "headroom": "More headroom",
            "throughput": "More throughput",
        }
        persisted_launch_priority = _launch_priority_preference()
        launch_priority = st.selectbox(
            "Launch priority",
            options=list(preference_labels.keys()),
            index=list(preference_labels.keys()).index(persisted_launch_priority),
            key=f"mm_launch_priority_{key_suffix}",
            format_func=lambda value: preference_labels.get(value, str(value).title()),
            help="Choose whether the default launch profile should bias toward balanced settings, extra memory headroom, or more throughput. This preference is remembered for the rest of the sandbox session.",
        )
        launch_priority = _remember_launch_priority_preference(launch_priority)
        default_profile = _default_resource_profile_name(rec.resource_advisor, preference=launch_priority)
        default_index = profile_options.index(default_profile) if default_profile in profile_options else 0
        selected_launch_profile = st.selectbox(
            "Launch profile",
            options=profile_options,
            index=default_index,
            key=f"mm_launch_profile_{key_suffix}",
            help="Prefill engine launch settings from the shared llm_engines resource advisor.",
        )
        selected_launch_extra = _resource_profile_engine_extra(rec.resource_advisor, selected_launch_profile, engine_type="vllm")
        if selected_launch_extra:
            st.caption(
                f"Default profile for {preference_labels.get(launch_priority, launch_priority)}: `{default_profile}`. Selected profile settings will be written into llm_engines.yaml for this engine."
            )

    with col_btn:
        st.write("")  # Vertical alignment spacer
        if rec.engine == "ollama":
            tag = f"{model.name.lower()}:{rec.quantization.lower()}"
            if st.button(f"Pull via Ollama", key=f"mm_pull_{key_suffix}"):
                _do_ollama_pull(tag, engine_name, rec)
        elif rec.engine == "llama_cpp":
            # llama_cpp: must download the GGUF file, then use llama-server
            default_dir = default_local_model_dir(model.repo_id)
            target_dir = st.text_input(
                "Download directory",
                value=str(default_dir),
                key=f"mm_dl_dir_{key_suffix}",
                help="Where to save the GGUF file. llama-server loads it directly from this path.",
            )
            # Show what the gguf_path will be (best-guess filename)
            gguf_filename = f"{model.name.lower()}-{rec.quantization.lower()}.gguf"
            gguf_path_preview = str(Path(target_dir) / gguf_filename)
            st.caption(f"Expected GGUF path: `{gguf_path_preview}`")

            launch_cfg = {
                "type": "llama_cpp",
                "gguf_path": gguf_path_preview,
                "base_url": "http://127.0.0.1:8080/v1",
                "max_context": 16384,
                "n_gpu_layers": rec.num_gpu_layers or 0,
            }
            launch_cmd = build_llama_cpp_launch_command(launch_cfg) or ""
            if launch_cmd:
                st.info(f"After download, start with:\n```bash\n{launch_cmd}\n```")

            if st.button("Download GGUF + register", key=f"mm_dl_llama_{key_suffix}"):
                _do_llama_cpp_download_and_register(
                    model, engine_name, rec,
                    Path(target_dir).expanduser(),
                    gguf_filename,
                )
        else:
            default_dir = default_local_model_dir(model.repo_id)
            target_dir = st.text_input(
                "Download directory",
                value=str(default_dir),
                key=f"mm_dl_dir_{key_suffix}",
                help="Engram-managed local path where this Hugging Face repo will be downloaded.",
            )
            st.info(
                f"Recommended flow for vLLM: download the repo into Engram's local model store, "
                f"then start vLLM against that local path.\n\n"
                f"Example:\n```\nvllm serve {target_dir}\n```"
            )
            col_dl, col_reg = st.columns(2)
            with col_dl:
                if st.button("Download + register", key=f"mm_dl_reg_{key_suffix}"):
                    _do_hf_download_and_register(
                        model,
                        engine_name,
                        rec,
                        Path(target_dir).expanduser(),
                        launch_profile_name=selected_launch_profile,
                        launch_profile_extra=selected_launch_extra,
                    )
            with col_reg:
                if st.button("Register repo only", key=f"mm_reg_{key_suffix}"):
                    _do_register(
                        engine_name,
                        rec.engine,
                        model.repo_id,
                        rec,
                        launch_profile_name=selected_launch_profile,
                        launch_profile_extra=selected_launch_extra,
                    )


# ------------------------------------------------------------------
# Download/register action helpers
# ------------------------------------------------------------------

def _do_ollama_pull(tag: str, engine_name: str, rec: FormatRecommendation):
    """Pull model via Ollama and register."""
    with st.spinner(f"Pulling {tag} via Ollama (this may take a while)..."):
        ok = download_ollama_model(tag)
    if ok:
        register_model_in_config(
            engine_name=engine_name,
            engine_type="ollama",
            model_id=tag,
            config_path=_config_path(),
            num_gpu=rec.num_gpu_layers if not rec.fits_in_vram else None,
        )
        st.success(f"Pulled **{tag}** and registered as **{engine_name}**.")
        st.info("Add it to a profile in the **Profile Editor** below.")
    else:
        st.error(f"Failed to pull {tag}. Is Ollama running?")


def _do_hf_download_and_register(
    model: HFModelInfo,
    engine_name: str,
    rec: FormatRecommendation,
    target_dir: Path,
    *,
    launch_profile_name: str = "",
    launch_profile_extra: Optional[Dict[str, Any]] = None,
):
    """Download a HF model into Engram-managed storage and register the local path."""
    with st.spinner(f"Downloading {model.repo_id} to {target_dir} ..."):
        result = download_hf_model(model.repo_id, local_dir=target_dir)
    if not result.success:
        st.error(f"Download failed: {result.error or 'unknown error'}")
        return
    else:
        fit = _score_model_fit(
            model_text=model.repo_id,
            hf_repo_id=model.repo_id,
            local_model_dir=str(target_dir),
            backend="vllm",
        )

        if fit["fit"] == "likely_oom":
            st.warning(
                "Downloaded successfully. This model is likely to OOM with vLLM on the detected GPU. "
                "Ollama may work better, though speed may be lower."
            )
        elif fit["fit"] == "borderline":
            st.info(
                "Downloaded successfully. This model is a borderline fit for vLLM on the detected GPU."
            )

    preview_cfg, preview_notes = _vllm_launch_preview_cfg(
        source=str(result.local_dir),
        engine_name=engine_name,
        launch_profile_extra=launch_profile_extra,
    )

    register_model_in_config(
        engine_name=engine_name,
        engine_type="vllm",
        model_id=str(result.local_dir),
        config_path=_config_path(),
        num_gpu=rec.num_gpu_layers if not rec.fits_in_vram else None,
        extra={
            "hf_repo_id": model.repo_id,
            "local_model_dir": str(result.local_dir),
            "managed": False,
            "resource_advisor": list(rec.resource_advisor or []),
            **dict(launch_profile_extra or {}),
            "launch": dict(preview_cfg.get("launch") or {}),
        },
    )
    st.success(f"Downloaded **{model.repo_id}** to **{result.local_dir}** and registered **{engine_name}**.")
    if launch_profile_name:
        st.caption(f"Applied launch profile: `{launch_profile_name}`")
    launch_cmd = build_vllm_launch_command(preview_cfg)
    if launch_cmd:
        st.caption("Start vLLM with:")
        st.code(launch_cmd, language="bash")
    for note in preview_notes:
        st.caption(note)
    _render_resource_advisor_profiles(rec.resource_advisor)


def _do_llama_cpp_download_and_register(
    model: HFModelInfo,
    engine_name: str,
    rec: FormatRecommendation,
    target_dir: Path,
    gguf_filename: str,
):
    """Download a GGUF file from HF and register as a llama_cpp engine.

    Uses ``allow_patterns`` to fetch only GGUF files matching the
    recommended quantization rather than the full repo snapshot.
    After download, scans for the actual ``.gguf`` file, writes it as
    ``gguf_path`` in the engine config, and shows the ready-to-run
    ``llama-server`` launch command.
    """
    # Only fetch GGUF files matching the quantization — avoids pulling
    # safetensors shards, tokenizer data, etc. from mixed repos.
    quant = rec.quantization
    allow_patterns = [
        f"*{quant}*.gguf",
        f"*{quant.lower()}*.gguf",
        f"*.gguf",           # broad fallback: some repos use only one GGUF
    ]

    with st.spinner(f"Downloading {model.repo_id} ({quant}) GGUF to {target_dir} …"):
        result = download_hf_model(
            model.repo_id,
            local_dir=target_dir,
            allow_patterns=allow_patterns,
        )

    if not result.success:
        st.error(f"Download failed: {result.error or 'unknown error'}")
        return

    # Discover the downloaded GGUF file
    gguf_files = sorted(target_dir.glob("**/*.gguf"))
    if not gguf_files:
        st.warning(
            "Download completed but no `.gguf` file was found under "
            f"`{target_dir}`. The repo may use an unexpected filename. "
            "Set `gguf_path` manually in `llm_engines.yaml`."
        )
        gguf_path = str(target_dir / gguf_filename)
    else:
        # Prefer a file whose name contains the quantization string
        matched = [f for f in gguf_files if quant.lower() in f.name.lower()]
        chosen = matched[0] if matched else gguf_files[0]
        gguf_path = str(chosen)
        if len(gguf_files) > 1:
            st.caption(
                f"Multiple GGUF files found — using `{chosen.name}`. "
                "Change `gguf_path` in `llm_engines.yaml` to select a different variant."
            )

    n_gpu = rec.num_gpu_layers or 0
    register_model_in_config(
        engine_name=engine_name,
        engine_type="llama_cpp",
        model_id=engine_name,
        config_path=_config_path(),
        num_gpu=n_gpu,
        extra={
            "gguf_path": gguf_path,
            "hf_repo_id": model.repo_id,
        },
    )

    launch_cmd = build_llama_cpp_launch_command({
        "type": "llama_cpp",
        "gguf_path": gguf_path,
        "base_url": "http://127.0.0.1:8080/v1",
        "max_context": 16384,
        "n_gpu_layers": n_gpu,
    })

    st.success(
        f"Downloaded **{model.repo_id}** ({quant}) and registered "
        f"**{engine_name}** as a llama.cpp engine."
    )
    st.caption(f"GGUF: `{gguf_path}`")
    st.caption(
        f"GPU offload: {'CPU-only (n_gpu_layers=0)' if n_gpu == 0 else f'{n_gpu} layers on GPU, rest on CPU'}"
    )
    if launch_cmd:
        st.markdown("**Start llama-server with:**")
        st.code(launch_cmd, language="bash")
    st.info("Add this engine to a failover profile in the **Profile Editor** below.")


def _do_register(
    engine_name: str,
    engine_type: str,
    model_id: str,
    rec: FormatRecommendation,
    *,
    launch_profile_name: str = "",
    launch_profile_extra: Optional[Dict[str, Any]] = None,
):
    """Register a model without pulling (for vLLM or pre-downloaded)."""
    extra = dict(launch_profile_extra or {})
    preview_cfg: Dict[str, Any] | None = None
    preview_notes: List[str] = []
    if str(engine_type).lower().strip() == "vllm":
        preview_cfg, preview_notes = _vllm_launch_preview_cfg(
            source=str(model_id),
            engine_name=engine_name,
            launch_profile_extra=launch_profile_extra,
        )
        extra["launch"] = dict(preview_cfg.get("launch") or {})

    register_model_in_config(
        engine_name=engine_name,
        engine_type=engine_type,
        model_id=model_id,
        config_path=_config_path(),
        num_gpu=rec.num_gpu_layers if not rec.fits_in_vram else None,
        extra=extra,
    )
    st.success(f"Registered **{engine_name}** ({engine_type}/{model_id}).")
    if launch_profile_name:
        st.caption(f"Applied launch profile: `{launch_profile_name}`")
    if preview_cfg is not None:
        launch_cmd = build_vllm_launch_command(preview_cfg)
        if launch_cmd:
            st.caption("Start vLLM with:")
            st.code(launch_cmd, language="bash")
        for note in preview_notes:
            st.caption(note)
    _render_resource_advisor_profiles(rec.resource_advisor)


# ------------------------------------------------------------------
# Local import panel
# ------------------------------------------------------------------

def _render_local_import():
    """Import a model from local filesystem."""
    st.subheader("Import Local Model")
    st.caption(
        "Point to a GGUF file or a directory containing safetensors. "
        "Useful in air-gapped environments or for testing your own models."
    )

    model_path = st.text_input(
        "Model path",
        placeholder="/path/to/model.gguf or /path/to/model-directory/",
        key="mm_local_path",
    )

    if st.button("Scan", key="mm_local_scan", disabled=not model_path):
        p = Path(model_path).expanduser()
        if not p.exists():
            st.error(f"Path does not exist: {p}")
            st.session_state[_K_LOCAL] = None
            return

        result = scan_local_model(p)
        if result is None:
            st.error("No recognized model files found (expected .gguf or .safetensors).")
            st.session_state[_K_LOCAL] = None
        else:
            st.session_state[_K_LOCAL] = result

    local: Optional[LocalModelInfo] = st.session_state.get(_K_LOCAL)
    if local is None:
        return

    st.write(f"**Name:** {local.name}")
    st.write(f"**Format:** {local.format}")
    st.write(f"**Size:** {local.size_gb:.2f} GB")
    st.write(f"**Files:** {', '.join(local.files[:5])}"
             + (f" (+{len(local.files)-5} more)" if len(local.files) > 5 else ""))

    engine_name = st.text_input(
        "Engine name for this model",
        value=local.name.lower().replace("-", "_").replace(" ", "_"),
        key="mm_local_eng_name",
    )

    if local.format == "gguf":
        gguf_file = local.path if local.path.is_file() else local.path / local.files[0]

        st.markdown("**Option A — Ollama** (simpler, no GPU layer control)")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Import to Ollama", key="mm_local_ollama"):
                with st.spinner(f"Importing {gguf_file.name} to Ollama..."):
                    ok = import_gguf_to_ollama(gguf_file, engine_name)
                if ok:
                    register_model_in_config(
                        engine_name=engine_name,
                        engine_type="ollama",
                        model_id=engine_name,
                        config_path=_config_path(),
                    )
                    st.success(f"Imported and registered as **{engine_name}**.")
                else:
                    st.error("Import failed. Check that Ollama is running.")
        with col2:
            if st.button("Register only (no import)", key="mm_local_reg_gguf"):
                register_model_in_config(
                    engine_name=engine_name,
                    engine_type="ollama",
                    model_id=engine_name,
                    config_path=_config_path(),
                )
                st.success(f"Registered **{engine_name}**. You'll need to import it to Ollama manually.")

        st.markdown("**Option B — llama.cpp / llama-server** (split GPU+CPU offload, no import needed)")
        n_gpu = st.number_input(
            "GPU layers (--n-gpu-layers)",
            min_value=0, max_value=999, value=0,
            key="mm_local_llama_gpu_layers",
            help="0 = full CPU. Set to the number of transformer layers to offload to GPU. "
                 "RTX 3090 + Q4_K_M 32B ≈ 40 layers.",
        )
        preview_cfg = {
            "type": "llama_cpp",
            "gguf_path": str(gguf_file),
            "base_url": "http://127.0.0.1:8080/v1",
            "max_context": 16384,
            "n_gpu_layers": int(n_gpu),
        }
        launch_cmd = build_llama_cpp_launch_command(preview_cfg)
        if launch_cmd:
            st.caption("Launch command preview:")
            st.code(launch_cmd, language="bash")

        if st.button("Register for llama.cpp", key="mm_local_reg_llama"):
            register_model_in_config(
                engine_name=engine_name,
                engine_type="llama_cpp",
                model_id=engine_name,
                config_path=_config_path(),
                num_gpu=int(n_gpu),
                extra={"gguf_path": str(gguf_file)},
            )
            st.success(f"Registered **{engine_name}** as a llama.cpp engine.")
            st.caption(f"GGUF: `{gguf_file}`  |  n_gpu_layers: {n_gpu}")
            if launch_cmd:
                st.info(f"Start llama-server with:\n```bash\n{launch_cmd}\n```")

    elif local.format == "safetensors":
        st.info(
            f"Safetensors model detected. Start vLLM with:\n"
            f"```\nvllm serve {local.path}\n```"
        )
        if st.button("Register for vLLM", key="mm_local_reg_st"):
            register_model_in_config(
                engine_name=engine_name,
                engine_type="vllm",
                model_id=str(local.path),
                config_path=_config_path(),
            )
            st.success(f"Registered **{engine_name}** pointing to {local.path}.")

    elif local.format == "pytorch":
        st.info("PyTorch format detected. vLLM can serve this. Start with:\n"
                f"```\nvllm serve {local.path}\n```")
        if st.button("Register for vLLM", key="mm_local_reg_pt"):
            register_model_in_config(
                engine_name=engine_name,
                engine_type="vllm",
                model_id=str(local.path),
                config_path=_config_path(),
            )
            st.success(f"Registered **{engine_name}**.")

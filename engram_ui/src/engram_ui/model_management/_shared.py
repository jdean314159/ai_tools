"""Shared helpers for the model_management package.

Config IO, session-state keys, badges, formatters, resource-profile logic,
endpoint probing, vLLM launch preview, engine inventory building, and
system-recommendation rendering. Used by 2+ of the four section modules.

Author: Jeffrey Dean
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import yaml

from engram.engine.model_manager import (
    score_model_fit as _score_model_fit,
)
from engram.engine.model_discovery import list_ollama_models, list_vllm_models
from engram.engine.runtime_status import (
    build_vllm_launch_command,
    classify_runtime_state,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Session state keys (namespaced to avoid collisions with app.py)
# ------------------------------------------------------------------

_K_SYSTEM = "mm_system_info"
_K_SEARCH = "mm_search_results"
_K_LOCAL = "mm_local_scan_result"
_K_LAUNCH_PRIORITY = "mm_launch_priority_default"


# ------------------------------------------------------------------
# Config IO
# ------------------------------------------------------------------

def _config_path() -> Path:
    return Path("~/.engram/llm_engines.yaml").expanduser()


def _load_config() -> Dict[str, Any]:
    p = _config_path()
    if not p.exists():
        # Fall back to bundled
        import engram.engine
        p = Path(engram.engine.__file__).resolve().parent / "llm_engines.yaml"
    if not p.exists():
        return {}
    with open(p) as f:
        return yaml.safe_load(f) or {}


def _save_config(cfg: Dict[str, Any]):
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)


# ------------------------------------------------------------------
# Launch-priority preference (session-persistent)
# ------------------------------------------------------------------

def _launch_priority_preference() -> str:
    """Return the persisted sandbox launch-priority preference for this session."""
    preference = str(st.session_state.get(_K_LAUNCH_PRIORITY, "balanced") or "balanced").strip().lower()
    if preference not in {"balanced", "headroom", "throughput"}:
        preference = "balanced"
    st.session_state[_K_LAUNCH_PRIORITY] = preference
    return preference


def _remember_launch_priority_preference(preference: str) -> str:
    """Persist the user's launch-priority preference for later model selections in this session."""
    normalized = str(preference or "balanced").strip().lower()
    if normalized not in {"balanced", "headroom", "throughput"}:
        normalized = "balanced"
    st.session_state[_K_LAUNCH_PRIORITY] = normalized
    return normalized


# ------------------------------------------------------------------
# Resource-profile helpers
# ------------------------------------------------------------------

def _resource_profile_rows(resource_advisor: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for raw in list(resource_advisor or []):
        if not isinstance(raw, dict):
            continue
        estimate = raw.get("estimate") if isinstance(raw.get("estimate"), dict) else {}
        params = raw.get("parameters") if isinstance(raw.get("parameters"), dict) else {}
        optimizations = params.get("optimizations") if isinstance(params.get("optimizations"), dict) else {}

        settings: List[str] = []
        if params.get("gpu_memory_utilization") is not None:
            settings.append(f"gpu_memory_utilization={params['gpu_memory_utilization']}")
        if params.get("max_num_seqs") is not None:
            settings.append(f"max_num_seqs={params['max_num_seqs']}")
        if params.get("max_num_batched_tokens") is not None:
            settings.append(f"max_num_batched_tokens={params['max_num_batched_tokens']}")
        if optimizations:
            for key in ("speculative_decoding", "draft_model", "kv_cache_compression", "kv_cache_bits"):
                if optimizations.get(key) is not None:
                    settings.append(f"{key}={optimizations[key]}")

        estimated_total_mb = estimate.get("estimated_total_mb")
        headroom_mb = estimate.get("estimated_headroom_mb")
        rows.append({
            "profile": str(raw.get("profile") or "unknown"),
            "backend": str(raw.get("backend") or ""),
            "estimated": f"{float(estimated_total_mb) / 1024.0:.1f} GB" if estimated_total_mb is not None else "unknown",
            "headroom": f"{float(headroom_mb) / 1024.0:.1f} GB" if headroom_mb is not None else "unknown",
            "fits": "yes" if bool(estimate.get("fits")) else "no",
            "settings": ", ".join(settings) if settings else "(defaults)",
            "rationale": " ".join(str(item) for item in raw.get("rationale") or []),
        })
    return rows


def _default_resource_profile_name(
    resource_advisor: List[Dict[str, Any]],
    *,
    preference: str = "balanced",
) -> str:
    profiles = [raw for raw in list(resource_advisor or []) if isinstance(raw, dict)]
    if not profiles:
        return ""

    preferred_order = {
        "headroom": ("safe", "balanced", "aggressive"),
        "throughput": ("aggressive", "balanced", "safe"),
        "balanced": ("balanced", "safe", "aggressive"),
    }.get((preference or "balanced").strip().lower(), ("balanced", "safe", "aggressive"))

    for preferred in preferred_order:
        for raw in profiles:
            estimate = raw.get("estimate") if isinstance(raw.get("estimate"), dict) else {}
            if str(raw.get("profile") or "").lower() == preferred and bool(estimate.get("fits")):
                return str(raw.get("profile") or preferred)
    for raw in profiles:
        estimate = raw.get("estimate") if isinstance(raw.get("estimate"), dict) else {}
        if bool(estimate.get("fits")):
            return str(raw.get("profile") or "")
    return str(profiles[0].get("profile") or "")


def _selected_resource_profile(resource_advisor: List[Dict[str, Any]], profile_name: str) -> Dict[str, Any] | None:
    wanted = (profile_name or "").strip().lower()
    for raw in list(resource_advisor or []):
        if isinstance(raw, dict) and str(raw.get("profile") or "").lower() == wanted:
            return raw
    return None


def _resource_profile_engine_extra(
    resource_advisor: List[Dict[str, Any]],
    profile_name: str,
    *,
    engine_type: str = "vllm",
) -> Dict[str, Any]:
    raw = _selected_resource_profile(resource_advisor, profile_name)
    if raw is None or engine_type not in {"vllm", "openai_compatible"}:
        return {}
    params = raw.get("parameters") if isinstance(raw.get("parameters"), dict) else {}
    optimizations = params.get("optimizations") if isinstance(params.get("optimizations"), dict) else {}

    extra: Dict[str, Any] = {
        "launch_profile": str(raw.get("profile") or profile_name or "custom"),
    }
    for key in ("gpu_memory_utilization", "max_num_seqs", "max_num_batched_tokens"):
        if params.get(key) is not None:
            extra[key] = params[key]
    for key in ("speculative_decoding", "draft_model", "kv_cache_compression", "kv_cache_bits"):
        if optimizations.get(key) is not None:
            extra[key] = optimizations[key]
    return extra


# ------------------------------------------------------------------
# vLLM launch preview
# ------------------------------------------------------------------

def _vllm_launch_extra_args_from_settings(settings: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    args: List[str] = []
    notes: List[str] = []

    if settings.get("gpu_memory_utilization") is not None:
        args.extend(["--gpu-memory-utilization", str(settings["gpu_memory_utilization"])])
    if settings.get("max_num_seqs") is not None:
        args.extend(["--max-num-seqs", str(settings["max_num_seqs"])])
    if settings.get("max_num_batched_tokens") is not None:
        args.extend(["--max-num-batched-tokens", str(settings["max_num_batched_tokens"])])

    speculative_enabled = bool(settings.get("speculative_decoding"))
    draft_model = str(settings.get("draft_model") or "").strip()
    speculative_tokens = settings.get("speculative_tokens") or settings.get("num_speculative_tokens")
    if speculative_enabled and draft_model:
        spec_cfg: Dict[str, Any] = {"model": draft_model}
        if speculative_tokens is not None:
            spec_cfg["num_speculative_tokens"] = speculative_tokens
        args.extend(["--speculative-config", json.dumps(spec_cfg, separators=(",", ":"))])
    elif speculative_enabled:
        notes.append("Speculative decoding was requested, but no draft_model is available for a CLI preview.")

    kv_mode = settings.get("kv_cache_compression")
    if kv_mode:
        kv_bits = settings.get("kv_cache_bits")
        bits_note = f" ({kv_bits}-bit)" if kv_bits is not None else ""
        notes.append(f"KV cache compression '{kv_mode}'{bits_note} is recorded in config but has no generic vLLM serve flag preview.")

    return args, notes


def _vllm_launch_preview_cfg(
    *,
    source: str,
    engine_name: str,
    launch_profile_extra: Optional[Dict[str, Any]] = None,
    base_url: str = "http://localhost:8000/v1",
) -> Tuple[Dict[str, Any], List[str]]:
    launch_profile_extra = dict(launch_profile_extra or {})
    extra_args, notes = _vllm_launch_extra_args_from_settings(launch_profile_extra)
    cfg: Dict[str, Any] = {
        "type": "vllm",
        "model": engine_name,
        "local_model_dir": source,
        "base_url": base_url,
        "launch": {
            "source": source,
            "served_model_name": engine_name,
            "extra_args": extra_args,
        },
    }
    cfg.update(launch_profile_extra)
    return cfg, notes


def _render_resource_advisor_profiles(resource_advisor: List[Dict[str, Any]]) -> None:
    rows = _resource_profile_rows(resource_advisor)
    if not rows:
        return

    with st.expander("Launch profiles", expanded=False):
        st.caption("Shared engine-fit advisor output from llm_engines. Use these as starting points for launch parameters.")
        for row in rows:
            st.markdown(f"**{row['profile'].title()}** — {row['backend']} | estimated {row['estimated']} | headroom {row['headroom']} | fits: {row['fits']}")
            st.code(row["settings"], language="text")
            if row["rationale"]:
                st.caption(row["rationale"])


# ------------------------------------------------------------------
# Inventory / health helpers
# ------------------------------------------------------------------

def _profile_engine_order(cfg: Dict[str, Any], profile_name: str) -> List[str]:
    profiles = cfg.get("profiles", {}) or {}
    prof = profiles.get(profile_name) or {}
    return list(prof.get("engines") or [])


def _safe_exists(path_str: str) -> Optional[bool]:
    if not path_str:
        return None
    try:
        return Path(path_str).expanduser().exists()
    except Exception:
        return None


def _endpoint_status(url: str, kind: str) -> Tuple[bool, List[str], str]:
    try:
        if kind == "ollama":
            models = list_ollama_models(url)
            return True, [m.id for m in models], ""
        models = list_vllm_models(url)
        return True, [m.id for m in models], ""
    except Exception as exc:
        return False, [], str(exc)


def _runtime_state_badge(state: str) -> str:
    s = (state or "").lower().strip()
    if s == "running":
        return "🟢 Running"
    if s in {"reachable", "degraded"}:
        return "🟡 Reachable"
    if s == "wrong_model":
        return "🟠 Wrong model"
    if s in {"not_running", "unreachable"}:
        return "🔴 Not running"
    return "⚪ Unknown"


def _engine_resource_advisor(engine_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    advisor = engine_cfg.get("resource_advisor")
    if isinstance(advisor, list):
        return [dict(item) for item in advisor if isinstance(item, dict)]
    return []


def _apply_launch_profile_to_engine(
    engine_name: str,
    *,
    profile_name: str,
    resource_advisor: List[Dict[str, Any]],
) -> bool:
    settings = _resource_profile_engine_extra(resource_advisor, profile_name, engine_type="vllm")
    if not settings:
        return False

    cfg = _load_config()
    engines = cfg.setdefault("engines", {})
    engine_cfg = dict(engines.get(engine_name) or {})
    preview_cfg, _notes = _vllm_launch_preview_cfg(
        source=str(
            engine_cfg.get("local_model_dir")
            or ((engine_cfg.get("launch") or {}).get("source") if isinstance(engine_cfg.get("launch"), dict) else "")
            or engine_cfg.get("hf_repo_id")
            or engine_cfg.get("model")
            or ""
        ),
        engine_name=str(engine_cfg.get("model") or engine_name),
        launch_profile_extra=settings,
        base_url=str(engine_cfg.get("base_url") or "http://localhost:8000/v1"),
    )
    engine_cfg.update(settings)
    engine_cfg["resource_advisor"] = list(resource_advisor or [])
    if preview_cfg.get("launch"):
        engine_cfg["launch"] = dict(preview_cfg.get("launch") or {})
    engines[engine_name] = engine_cfg
    _save_config(cfg)
    return True


def _render_vllm_launch_guidance(row: Dict[str, Any]) -> None:
    backend = str(row.get("backend") or "").lower().strip()
    is_vllm = backend in {"vllm", "openai-compatible", "openai_compatible"}
    is_llama_cpp = backend in {"llama_cpp", "llama-cpp", "llamacpp"}

    if not is_vllm and not is_llama_cpp:
        return

    launch_command = row.get("launch_command")
    expected_model = row.get("model") or ""
    endpoint = row.get("endpoint") or ""

    if expected_model:
        st.caption(f"Expected served model: `{expected_model}`")
    if endpoint:
        st.caption(f"Expected endpoint: `{endpoint}`")

    if is_llama_cpp:
        # Show llama-specific metadata
        gguf = row.get("gguf_path") or "(not set)"
        n_gpu = row.get("n_gpu_layers", 0)
        gpu_note = (
            "CPU-only" if int(n_gpu) == 0
            else f"split GPU+CPU ({n_gpu} layers on GPU)" if int(n_gpu) < 999
            else "full GPU"
        )
        st.caption(f"GGUF: `{gguf}`  |  Offload: {gpu_note}")

    if launch_command:
        label = "Launch command" if is_vllm else "llama-server launch command"
        with st.expander(label, expanded=False):
            st.code(launch_command, language="bash")
    elif is_vllm:
        st.caption("No launch metadata available. Add `launch.source` to this engine config to generate a vLLM command.")
    else:
        st.caption("No launch command available. Set `gguf_path` in this engine config.")


def _build_engine_inventory(cfg: Dict[str, Any], selected_profile: str) -> List[Dict[str, Any]]:
    engines_cfg = cfg.get("engines", {}) or {}
    selected_engines = set(_profile_engine_order(cfg, selected_profile))

    endpoint_cache: Dict[Tuple[str, str], Tuple[bool, List[str], str]] = {}
    rows: List[Dict[str, Any]] = []

    for name, ecfg in sorted(engines_cfg.items()):
        etype = str(ecfg.get("type") or "").lower().strip()
        base_url = str(ecfg.get("base_url") or "").strip()
        model = str(ecfg.get("model") or "")
        local_model_dir = str(ecfg.get("local_model_dir") or "")
        hf_repo_id = str(ecfg.get("hf_repo_id") or "")

        if etype == "ollama":
            family = "ollama"
        elif any(k in (model + " " + hf_repo_id + " " + local_model_dir).lower() for k in ("awq", "gptq", "exl2")):
            family = "transformers-quantized"
        elif any(k in (model + " " + hf_repo_id + " " + local_model_dir).lower() for k in ("gguf", "q3_k", "q4_k", "q5_k", "q6_k")):
            family = "gguf"
        elif etype in {"vllm", "openai", "openai-compatible", "openai_compatible"}:
            family = "openai-compatible"
        elif etype in {"llama_cpp", "llama-cpp", "llamacpp"}:
            family = "llama.cpp"
        else:
            family = etype or "unknown"

        downloaded = _safe_exists(local_model_dir) if local_model_dir else None
        reachable = None
        served = None
        endpoint_error = ""
        served_models: List[str] = []

        if base_url and etype in {"ollama", "vllm", "openai", "openai-compatible",
                                    "openai_compatible", "llama_cpp", "llama-cpp", "llamacpp"}:
            kind = "ollama" if etype == "ollama" else "vllm"
            cache_key = (kind, base_url if kind == "vllm" else base_url.replace('/v1', '').rstrip('/'))
            if cache_key not in endpoint_cache:
                endpoint_cache[cache_key] = _endpoint_status(cache_key[1], kind)
            reachable, served_models, endpoint_error = endpoint_cache[cache_key]
            served = bool(model and model in served_models) if reachable else False

        launch_command = build_vllm_launch_command(ecfg)
        if not launch_command and etype in {"llama_cpp", "llama-cpp", "llamacpp"}:
            from engram.engine.runtime_status import build_llama_cpp_launch_command
            launch_command = build_llama_cpp_launch_command(ecfg)
        runtime_state, runtime_message = classify_runtime_state(
            etype,
            reachable,
            served,
            base_url,
            model,
        )

        rows.append({
            "engine_name": name,
            "backend": etype or "?",
            "artifact_family": family,
            "model": model,
            "hf_repo_id": hf_repo_id,
            "local_model_dir": local_model_dir,
            "downloaded": downloaded,
            "endpoint": base_url,
            "reachable": reachable,
            "served": served,
            "selected": name in selected_engines,
            "served_models": served_models,
            "endpoint_error": endpoint_error,
            "launch_command": launch_command,
            "runtime_state": runtime_state,
            "runtime_message": runtime_message,
            # llama_cpp-specific metadata
            "gguf_path": str(ecfg.get("gguf_path") or ""),
            "n_gpu_layers": ecfg.get("n_gpu_layers", 0),
        })
    return rows


# ------------------------------------------------------------------
# Badge / label / icon helpers
# ------------------------------------------------------------------

def _render_status_badge(label: str, ok: Optional[bool]) -> str:
    if ok is None:
        return f"{label}: n/a"
    return f"{label}: {'yes' if ok else 'no'}"


def _fit_badge_label(fit: str) -> str:
    return {
        "good": "Good fit",
        "borderline": "Borderline",
        "blocked_now": "Blocked by current VRAM use",
        "better_ollama": "Better with Ollama",
        "likely_oom": "Likely too large",
        "remote": "Remote runtime",
        "unknown": "Unknown fit",
    }.get(fit, "Unknown fit")


def _runtime_badge_label(runtime: str) -> str:
    return {
        "vllm": "Best with vLLM",
        "ollama": "Better with Ollama",
        "remote": "Remote / cloud",
    }.get(runtime, "Runtime unclear")


def _status_icon(status: str) -> str:
    s = (status or "").lower().strip()
    if s in {"reachable", "ok", "available", "served"}:
        return "🟢"
    if s in {"warning", "degraded"}:
        return "🟡"
    if s in {"unreachable", "failed", "missing"}:
        return "🔴"
    return "⚪"


def _friendly_endpoint_error(endpoint: str, err_text: str) -> str:
    text = (err_text or "").lower()

    if "401" in text or "unauthorized" in text:
        return "API key missing or invalid."

    if "connection refused" in text or "failed to establish a new connection" in text:
        if "8000" in endpoint:
            return "vLLM server not running."
        if "11434" in endpoint:
            return "Ollama service not running."
        return "Endpoint is not running."

    if "timed out" in text or "timeout" in text:
        return "Endpoint timed out."

    if "name or service not known" in text or "temporary failure in name resolution" in text:
        return "Host could not be resolved."

    return "Endpoint unavailable."


def _maybe_render_model_list(models: list[str], backend: str, max_inline: int = 3) -> None:
    models = models or []
    if not models:
        if (backend or "").lower().strip() == "ollama":
            st.caption("No models available in Ollama.")
        else:
            st.caption("No models served.")
        return

    noun = "models available" if (backend or "").lower().strip() == "ollama" else "models served"

    if len(models) <= max_inline:
        st.caption(", ".join(models))
        return

    st.caption(f"{len(models)} {noun}")
    with st.expander("Show models", expanded=False):
        for m in models:
            st.write(f"`{m}`")


# ------------------------------------------------------------------
# System recommendations panel
# ------------------------------------------------------------------

def _render_system_recommendations(cfg: Dict[str, Any]) -> None:
    st.subheader("Recommended for this system")

    engines_cfg = cfg.get("engines", {}) or {}

    scored = []
    for engine_name, ecfg in engines_cfg.items():
        model_text = str(ecfg.get("model") or "")
        hf_repo_id = str(ecfg.get("hf_repo_id") or "")
        local_model_dir = str(ecfg.get("local_model_dir") or "")

        fit = _score_model_fit(
            model_text,
            hf_repo_id,
            local_model_dir,
            backend=str(ecfg.get("type") or ""),
            n_gpu_layers=int(ecfg.get("n_gpu_layers") or 0),
        )
        scored.append({
            "engine_name": engine_name,
            "backend": str(ecfg.get("type") or ""),
            "model": model_text,
            "hf_repo_id": hf_repo_id,
            "local_model_dir": local_model_dir,
            **fit,
        })

    best_vllm = [r for r in scored if r["fit"] in {"good", "borderline"} and r["runtime"] == "vllm"]
    blocked_now = [r for r in scored if r["fit"] == "blocked_now"]
    better_ollama = [r for r in scored if r["fit"] == "better_ollama"]
    risky = [r for r in scored if r["fit"] == "likely_oom"]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Available now with vLLM**")
        if not best_vllm:
            st.caption("No strong vLLM candidates detected.")
        for r in best_vllm[:5]:
            st.write(f"**{r['engine_name']}**")
            st.caption(r["model"] or r["hf_repo_id"] or r["local_model_dir"])
            st.caption(r["rationale"])

    with col2:
        st.markdown("**Currently blocked by loaded model**")
        if not blocked_now:
            st.caption("No models are currently blocked by loaded GPU memory.")
        for r in blocked_now[:5]:
            st.write(f"**{r['engine_name']}**")
            st.caption(r["model"] or r["hf_repo_id"] or r["local_model_dir"])
            st.caption("Good candidate for this machine, but current GPU memory is already occupied by another runtime.")

    with col3:
        st.markdown("**Better with Ollama / Too large**")

        if better_ollama:
            st.caption("These models are better candidates for Ollama on this system.")
            for r in better_ollama[:3]:
                st.write(f"**{r['engine_name']}**")
                st.caption(r["model"] or r["hf_repo_id"] or r["local_model_dir"])
                st.caption(r["rationale"])

        if risky:
            if better_ollama:
                st.write("")
            st.caption("These models are likely too large for reliable local use on the detected system.")
            for r in risky[:5]:
                st.write(f"**{r['engine_name']}**")
                st.caption(r["model"] or r["hf_repo_id"] or r["local_model_dir"])
                st.caption("Likely too large for reliable local use on the detected system.")

        if not better_ollama and not risky:
            st.caption("No Ollama-oriented or high-risk models detected.")

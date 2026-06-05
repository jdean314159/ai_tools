from __future__ import annotations

import json

from diagnostics_agent import (
    ChatTurn,
    CollectionReadError,
    DiagnosticsOrchestrator,
    FollowupChat,
    LogInterpreter,
    LogTriage,
    SandboxConfig,
    journalctl_collector,
    list_local_models,
    make_staging_sandbox,
)
from diagnostics_agent.engine_select import EngineChoice, build_engine
from diagnostics_agent.models import ModelDiscoveryError, detect_available_vram_bytes
from llm_engines import OllamaModelResolutionError, resolve_ollama_gguf_path


_TIME_WINDOWS = {
    "Last 1h": "-1h",
    "Last 6h": "-6h",
    "Last 24h": "-24h",
    "Last 3 days": "-3d",
}
_PRIORITIES = ("emergency", "alert", "critical", "error", "warning")
_KV_CACHE_TYPES = ("f16", "q8_0", "q4_0")


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="Diagnostics Agent", layout="wide")
    st.title("Diagnostics Agent")

    vram = detect_available_vram_bytes()
    engine_choice = _render_engine_choice(st, vram)

    priority = st.selectbox("Priority", _PRIORITIES, index=_PRIORITIES.index("warning"))
    window_label = st.selectbox("Time window", list(_TIME_WINDOWS), index=2)
    run_clicked = st.button("Run diagnostics", disabled=engine_choice is None)

    if run_clicked and engine_choice is not None:
        with st.spinner("Running diagnostics..."):
            try:
                collector = journalctl_collector(priority=priority, since=_TIME_WINDOWS[window_label])
                engine = build_engine(engine_choice)
                result = DiagnosticsOrchestrator(
                    collector=collector,
                    triage=LogTriage(),
                    interpreter=LogInterpreter(engine),
                    sandbox=make_staging_sandbox(),
                ).run()
                st.session_state["diagnostics_result"] = result
                st.session_state["diagnostics_engine_choice"] = engine_choice
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
        _render_followup_chat(st, result)


def _render_engine_choice(st, vram: int | None) -> EngineChoice | None:
    backend = st.selectbox("Backend", ["ollama", "llamacpp", "vllm"])
    if vram is not None:
        st.caption(f"Detected free VRAM: {_format_bytes(vram)}")
    else:
        st.caption("Detected free VRAM: unknown")

    if backend == "ollama":
        base_url = st.text_input("Ollama base URL", value="http://localhost:11434")
        st.caption("Point at another machine's Ollama over the LAN; treated as local/trusted.")
        models = _discover_ollama_models(st, base_url, vram)
        selected_model = _select_ollama_model(st, models)
        if selected_model is None:
            return None
        choice = EngineChoice("ollama", selected_model, base_url=_optional_url(base_url))
        return _with_optional_ollama_fallback(st, choice, models, selected_model)

    if backend == "llamacpp":
        source = st.radio("Model source", ["Use an Ollama-managed model", "Custom GGUF path"])
        n_gpu_layers = int(st.number_input("n_gpu_layers", min_value=-1, value=0, step=1))
        st.caption("Raise n_gpu_layers to offload layers onto a small GPU; 0 is CPU only.")
        n_ctx_enabled = st.checkbox("Set n_ctx")
        n_ctx = int(st.number_input("n_ctx", min_value=512, value=4096, step=512)) if n_ctx_enabled else None
        n_batch = st.number_input(
            "n_batch",
            min_value=1,
            value=None,
            step=1,
            placeholder="default",
        )
        n_ubatch = st.number_input(
            "n_ubatch",
            min_value=1,
            value=None,
            step=1,
            placeholder="default",
        )
        n_batch = int(n_batch) if n_batch is not None else None
        n_ubatch = int(n_ubatch) if n_ubatch is not None else None
        cache_type_k = st.selectbox("KV cache K type", _KV_CACHE_TYPES, index=0)
        cache_type_v = st.selectbox("KV cache V type", _KV_CACHE_TYPES, index=0)
        flash_attn = st.checkbox(
            "Enable flash attention (required for quantized V cache)"
        )
        st.caption(
            "q8_0 K with f16 V is the conservative small-GPU setting; "
            "lower n_batch on constrained VRAM."
        )

        models = _discover_ollama_models(st, "http://localhost:11434", vram) if source.startswith("Use") else []
        selected_model = None
        if source.startswith("Use"):
            selected_model = _select_ollama_model(st, models)
            if selected_model is None:
                return None
            try:
                model_path = str(resolve_ollama_gguf_path(selected_model))
            except OllamaModelResolutionError as exc:
                st.error(str(exc))
                return None
            st.caption(model_path)
        else:
            model_path = st.text_input("GGUF path")
            if not model_path.strip():
                return None

        choice = EngineChoice(
            "llamacpp",
            model_path.strip(),
            n_gpu_layers=n_gpu_layers,
            n_ctx=n_ctx,
            n_batch=n_batch,
            n_ubatch=n_ubatch,
            cache_type_k=cache_type_k,
            cache_type_v=cache_type_v,
            flash_attn=flash_attn,
            think=False,
        )
        return _with_optional_ollama_fallback(st, choice, models, selected_model)

    model = st.text_input("vLLM served model name")
    base_url = st.text_input("vLLM endpoint", value="http://localhost:8000/v1")
    st.caption("vLLM serves models over an HTTP endpoint; Ollama GGUF models are not listed here.")
    if not model.strip() or not base_url.strip():
        return None
    return EngineChoice("vllm", model.strip(), base_url=base_url.strip())


def _discover_ollama_models(st, base_url: str, vram: int | None):
    try:
        models = list_local_models(ollama_host=base_url, available_vram_bytes=vram)
    except ModelDiscoveryError as exc:
        st.error(f"Ollama unreachable: {exc}")
        return []
    if not models:
        st.warning("No local Ollama models found.")
    return models


def _select_ollama_model(st, models) -> str | None:
    if not models:
        st.selectbox("Model", ["No local models found"], disabled=True)
        return None
    model_labels = {f"{model.name}  ({model.fit})": model.name for model in models}
    selected_label = st.selectbox("Model", list(model_labels))
    return model_labels[selected_label]


def _with_optional_ollama_fallback(
    st,
    choice: EngineChoice,
    models,
    default_model: str | None,
) -> EngineChoice:
    if not st.checkbox("Fall back to another Ollama on failure"):
        return choice
    fallback_url = st.text_input("Fallback Ollama base URL", value="http://localhost:11434")
    fallback_model = default_model
    if models:
        labels = {f"{model.name}  ({model.fit})": model.name for model in models}
        default_index = list(labels.values()).index(default_model) if default_model in labels.values() else 0
        fallback_label = st.selectbox("Fallback model", list(labels), index=default_index)
        fallback_model = labels[fallback_label]
    if not fallback_model:
        return choice
    return EngineChoice(
        choice.backend,
        choice.model,
        base_url=choice.base_url,
        n_gpu_layers=choice.n_gpu_layers,
        n_ctx=choice.n_ctx,
        n_batch=choice.n_batch,
        n_ubatch=choice.n_ubatch,
        cache_type_k=choice.cache_type_k,
        cache_type_v=choice.cache_type_v,
        flash_attn=choice.flash_attn,
        think=choice.think,
        fallback=EngineChoice("ollama", fallback_model, base_url=_optional_url(fallback_url)),
    )


def _optional_url(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned or cleaned == "http://localhost:11434":
        return None
    return cleaned


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

    if sandbox is not None and sandbox.truncated:
        cap = _format_bytes(SandboxConfig().max_output_bytes)
        st.warning(
            "Collected log output exceeded the "
            f"{cap} sandbox read limit and was truncated to the most recent {cap}. "
            "Older entries in the selected window were not analyzed. Narrow the "
            "time window, raise the priority filter, or increase max_output_bytes "
            "for a complete view."
        )

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


def _render_followup_chat(st, result) -> None:
    st.subheader("Follow-up Q&A")
    engine_choice = st.session_state.get("diagnostics_engine_choice")
    history = st.session_state.setdefault("followup_history", [])
    for turn in history:
        with st.chat_message(turn.role):
            st.write(turn.content)

    question = st.chat_input("Ask about these results", disabled=engine_choice is None)
    if question and engine_choice is not None:
        try:
            with st.spinner("Answering..."):
                reply = FollowupChat(build_engine(engine_choice)).answer(
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


def _format_bytes(byte_count: int) -> str:
    if byte_count % (1024 * 1024) == 0:
        return f"{byte_count // (1024 * 1024)} MiB"
    if byte_count % 1024 == 0:
        return f"{byte_count // 1024} KiB"
    return f"{byte_count} bytes"


if __name__ == "__main__":
    main()

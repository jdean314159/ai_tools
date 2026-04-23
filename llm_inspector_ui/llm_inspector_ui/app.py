from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from llm_inspector_ui.panels.compare_panel import render_compare_panel
from llm_inspector_ui.services.augmenter_service import AugmenterService
from llm_inspector_ui.services.engine_service import EngineService
from llm_inspector_ui.services.inspector_service import InspectorService
from llm_inspector_ui.services.orchestrator import RunPlan, WorkbenchOrchestrator
from llm_inspector_ui.services.profile_service import ProfileService
from llm_inspector_ui.state.models import WorkbenchProfile
from llm_inspector_ui.state.session_store import SessionStore
from llm_inspector_ui.panels.models_panel import render_models_panel
from llm_inspector_ui.services.engine_registry_bootstrap import bootstrap_llm_engines_registry
from llm_inspector_ui.panels.startup_panel import render_startup_panel

from llm_inspector_ui.utils.trace_access import (
    get_evidence,
    get_agent_events,
    get_agent_execution_rows,
    get_agent_execution_summary,
    get_agent_summary,
    get_events,
    get_final_prompt,
    get_metrics,
    get_retrieval_events,
    get_retrieval_summary,
    get_sections,
    get_signals,
    get_token_accounting,
)


APP_DIR = Path.home() / ".llm_inspector_ui"
DB_PATH = APP_DIR / "workbench.sqlite"


def get_engine_registry():
    return bootstrap_llm_engines_registry()


def init_services():
    if "session_store" not in st.session_state:
        st.session_state.session_store = SessionStore(DB_PATH)

    if "engine_service" not in st.session_state:
        st.session_state.engine_service = EngineService(registry=get_engine_registry())

    if "augmenter_service" not in st.session_state:
        st.session_state.augmenter_service = AugmenterService(
            engram_base_dir=APP_DIR / "memory",
            engram_project_id="inspector-ui",
            engram_project_type="programming_assistant",
        )

    if "inspector_service" not in st.session_state:
        st.session_state.inspector_service = InspectorService()

    if "profile_service" not in st.session_state:
        st.session_state.profile_service = ProfileService(st.session_state.session_store)

    if "orchestrator" not in st.session_state:
        st.session_state.orchestrator = WorkbenchOrchestrator(
            session_store=st.session_state.session_store,
            engine_service=st.session_state.engine_service,
            augmenter_service=st.session_state.augmenter_service,
            inspector_service=st.session_state.inspector_service,
        )


def ensure_current_session():
    store: SessionStore = st.session_state.session_store
    sessions = store.list_sessions()
    if "current_session_id" not in st.session_state or not st.session_state.current_session_id:
        if sessions:
            st.session_state.current_session_id = sessions[0].session_id
        else:
            session = store.create_session("Chat Lab")
            st.session_state.current_session_id = session.session_id


def _default_profile_values() -> dict[str, object]:
    return {
        "engine_id": "echo",
        "model_id": "echo",
        "engine_config": {},
        "engine_settings": {},
        "augmenter_ids": ["baseline"],
        "max_prompt_tokens": None,
        "reserve_output_tokens": 512,
        "augmenter_options": {
            "baseline": {
                "system_prompt": "",
            },
            "engram": {
                "base_dir": str(APP_DIR / "memory"),
                "project_id": "inspector-ui",
                "project_type": "programming_assistant",
            },
            "rag": {
                "config": None,
                "collection": "default",
                "system_prompt": "",
            },
        },
    }


def _profile_to_controls(profile: WorkbenchProfile) -> dict[str, object]:
    return {
        "engine_id": profile.engine_id,
        "model_id": profile.model_id,
        "engine_config": dict(profile.engine_config or {}),
        "engine_settings": dict(profile.engine_settings or {}),
        "augmenter_ids": list(profile.augmenter_ids),
        "max_prompt_tokens": profile.max_prompt_tokens,
        "reserve_output_tokens": profile.reserve_output_tokens,
        "augmenter_options": {
            "baseline": {
                "system_prompt": "",
                **dict((profile.augmenter_options or {}).get("baseline", {}) or {}),
            },
            "engram": {
                "base_dir": str(APP_DIR / "memory"),
                "project_id": "inspector-ui",
                "project_type": "programming_assistant",
                **dict((profile.augmenter_options or {}).get("engram", {}) or {}),
            },
            "rag": {
                "config": None,
                "collection": "default",
                "system_prompt": "",
                **dict((profile.augmenter_options or {}).get("rag", {}) or {}),
            },
        },
    }


def _normalize_model_choice(models, preferred_model_id):
    if not models:
        return None
    model_ids = [m.model_id for m in models]
    if preferred_model_id in model_ids:
        return preferred_model_id
    return models[0].model_id


def sidebar_controls():
    store: SessionStore = st.session_state.session_store
    engine_service: EngineService = st.session_state.engine_service
    augmenter_service: AugmenterService = st.session_state.augmenter_service
    profile_service: ProfileService = st.session_state.profile_service

    if "current_controls" not in st.session_state:
        st.session_state.current_controls = _default_profile_values()
    if "selected_profile_id" not in st.session_state:
        st.session_state.selected_profile_id = None

    st.sidebar.header("Session")

    sessions = store.list_sessions()
    session_map = {f"{s.title} [{s.session_id[:8]}]": s.session_id for s in sessions}
    current_session_id = st.session_state.current_session_id

    if sessions:
        selected_label = st.sidebar.selectbox(
            "Current session",
            options=list(session_map.keys()),
            index=max(
                0,
                next(
                    (idx for idx, s in enumerate(sessions) if s.session_id == current_session_id),
                    0,
                ),
            ),
            key="session_select",
        )
        st.session_state.current_session_id = session_map[selected_label]

    if st.sidebar.button("New session", use_container_width=True):
        session = store.create_session("Chat Lab")
        st.session_state.current_session_id = session.session_id
        st.rerun()

    st.sidebar.header("Profile")

    profiles = profile_service.list_profiles()
    profile_labels = ["(unsaved current settings)"] + [p.name for p in profiles]
    selected_profile_label = st.sidebar.selectbox(
        "Saved profiles",
        options=profile_labels,
        index=0 if st.session_state.selected_profile_id is None else (
            1 + next(
                (idx for idx, p in enumerate(profiles) if p.profile_id == st.session_state.selected_profile_id),
                -1,
            )
            if any(p.profile_id == st.session_state.selected_profile_id for p in profiles)
            else 0
        ),
        key="profile_select",
    )

    if selected_profile_label == "(unsaved current settings)":
        st.session_state.selected_profile_id = None
    else:
        selected_profile = next(p for p in profiles if p.name == selected_profile_label)
        st.session_state.selected_profile_id = selected_profile.profile_id

    profile_name = st.sidebar.text_input(
        "Profile name",
        value=selected_profile_label if selected_profile_label != "(unsaved current settings)" else "",
        key="profile_name_input",
    )

    col_save, col_load = st.sidebar.columns(2)
    with col_save:
        if st.button("Save", use_container_width=True):
            current = st.session_state.current_controls
            payload = dict(
                name=profile_name or "Unnamed profile",
                engine_id=current["engine_id"],
                model_id=current["model_id"],
                augmenter_ids=current["augmenter_ids"],
                engine_config=current["engine_config"],
                engine_settings=current["engine_settings"],
                augmenter_options=current["augmenter_options"],
                max_prompt_tokens=current["max_prompt_tokens"],
                reserve_output_tokens=current["reserve_output_tokens"],
            )
            if st.session_state.selected_profile_id:
                profile_service.update_profile(
                    st.session_state.selected_profile_id,
                    **payload,
                )
            else:
                created = profile_service.create_profile(**payload)
                st.session_state.selected_profile_id = created.profile_id
            st.rerun()

    with col_load:
        if st.button("Load", use_container_width=True):
            if st.session_state.selected_profile_id:
                loaded = profile_service.get_profile(st.session_state.selected_profile_id)
                if loaded is not None:
                    st.session_state.current_controls = _profile_to_controls(loaded)
            st.rerun()

    if st.session_state.selected_profile_id:
        col_dup, col_del = st.sidebar.columns(2)
        with col_dup:
            if st.button("Duplicate", use_container_width=True):
                duplicated = profile_service.duplicate_profile(
                    st.session_state.selected_profile_id,
                    new_name=(profile_name or "Profile") + " (copy)",
                )
                st.session_state.selected_profile_id = duplicated.profile_id
                st.session_state.current_controls = _profile_to_controls(duplicated)
                st.rerun()
        with col_del:
            if st.button("Delete", use_container_width=True):
                profile_service.delete_profile(st.session_state.selected_profile_id)
                st.session_state.selected_profile_id = None
                st.session_state.current_controls = _default_profile_values()
                st.rerun()

    if "ui_beginner_mode" not in st.session_state:
        st.session_state.ui_beginner_mode = True

    st.sidebar.header("Learning mode")
    st.session_state.ui_beginner_mode = st.sidebar.checkbox(
        "Beginner explanations",
        value=bool(st.session_state.ui_beginner_mode),
        help="Show plain-language guidance in the Compare and Startup panels.",
        key="global_beginner_mode_checkbox",
    )

    st.sidebar.header("Run settings")

    current = st.session_state.current_controls
    engines = engine_service.list_engines()
    engine_by_id = {e.engine_id: e for e in engines}
    engine_labels = {e.label: e.engine_id for e in engines}

    preferred_engine_id = current.get("engine_id") if isinstance(current, dict) else None
    selected_engine_id = preferred_engine_id if preferred_engine_id in engine_by_id else engines[0].engine_id
    selected_engine_label = next(label for label, engine_id in engine_labels.items() if engine_id == selected_engine_id)

    selected_engine_label = st.sidebar.selectbox(
        "Engine",
        options=list(engine_labels.keys()),
        index=list(engine_labels.keys()).index(selected_engine_label),
        key="engine_select",
    )
    engine_id = engine_labels[selected_engine_label]

    current_engine_config = current.get("engine_config", {}) if isinstance(current, dict) else {}
    engine_config = render_engine_config_controls(engine_service, engine_id, current_engine_config)

    selected_engine_health = engine_service.get_engine_health(engine_id, config=engine_config)
    if selected_engine_health.status == "error":
        st.sidebar.error(f"{selected_engine_health.label}: {selected_engine_health.message or 'Not ready'}")
    elif selected_engine_health.status == "warning":
        st.sidebar.warning(f"{selected_engine_health.label}: {selected_engine_health.message or 'Partially ready'}")
    else:
        st.sidebar.success(f"{selected_engine_health.label}: ready")

    models = engine_service.list_models(engine_id, config=engine_config)
    selected_model_id = _normalize_model_choice(models, current.get("model_id") if isinstance(current, dict) else None)

    engine_temperature = st.sidebar.number_input(
        "Temperature",
        min_value=0.0,
        max_value=2.0,
        value=float((current.get("engine_settings", {}) or {}).get("temperature", 0.0)),
        step=0.1,
        key="engine_temperature_input",
    )

    engine_max_output_tokens = st.sidebar.number_input(
        "Max output tokens",
        min_value=0,
        value=int((current.get("engine_settings", {}) or {}).get("max_output_tokens") or 0),
        help="0 means engine default.",
        key="engine_max_output_tokens_input",
    )

    if models:
        label_by_model_id = {m.model_id: m.label for m in models}
        selected_model_label = st.sidebar.selectbox(
            "Model",
            options=[label_by_model_id[m.model_id] for m in models],
            index=[m.model_id for m in models].index(selected_model_id),
            key="model_select",
        )
        model_id = next(m.model_id for m in models if m.label == selected_model_label)
    else:
        model_id = None
        st.sidebar.caption("No models listed for this engine.")

    available_augmenters = augmenter_service.list_augmenters()
    current_augmenters = current.get("augmenter_ids", ["baseline"]) if isinstance(current, dict) else ["baseline"]

    compare_mode = st.sidebar.checkbox(
        "Compare mode",
        value=len(current_augmenters) > 1,
        key="compare_mode_checkbox",
    )

    if compare_mode:
        default_compare = [a for a in current_augmenters if a in available_augmenters] or ["baseline"]
        augmenter_ids = st.sidebar.multiselect(
            "Augmenters",
            options=available_augmenters,
            default=default_compare,
            key="augmenter_multiselect",
        )
        if not augmenter_ids:
            augmenter_ids = ["baseline"]
    else:
        default_single = current_augmenters[0] if current_augmenters and current_augmenters[0] in available_augmenters else available_augmenters[0]
        augmenter_ids = [
            st.sidebar.selectbox(
                "Augmenter",
                options=available_augmenters,
                index=available_augmenters.index(default_single),
                key="augmenter_select",
            )
        ]

    max_prompt_tokens_value = current.get("max_prompt_tokens") if isinstance(current, dict) else None
    reserve_output_tokens_value = current.get("reserve_output_tokens", 512) if isinstance(current, dict) else 512

    max_prompt_tokens = st.sidebar.number_input(
        "Max prompt tokens",
        min_value=0,
        value=int(max_prompt_tokens_value or 0),
        help="0 means unspecified.",
        key="max_prompt_tokens_input",
    )
    reserve_output_tokens = st.sidebar.number_input(
        "Reserve output tokens",
        min_value=0,
        value=int(reserve_output_tokens_value),
        key="reserve_output_tokens_input",
    )

    baseline_options = current.get("augmenter_options", {}).get("baseline", {}) if isinstance(current, dict) else {}
    engram_options = current.get("augmenter_options", {}).get("engram", {}) if isinstance(current, dict) else {}
    rag_options = current.get("augmenter_options", {}).get("rag", {}) if isinstance(current, dict) else {}

    system_prompt = st.sidebar.text_area(
        "Baseline system prompt",
        value=baseline_options.get("system_prompt", ""),
        help="Used only by the baseline augmenter in this first pass.",
        key="baseline_system_prompt_input",
    )

    engram_base_dir = st.sidebar.text_input(
        "Engram base dir",
        value=engram_options.get("base_dir", str(APP_DIR / "memory")),
        key="engram_base_dir_input",
    )
    engram_project_id = st.sidebar.text_input(
        "Engram project id",
        value=engram_options.get("project_id", "inspector-ui"),
        key="engram_project_id_input",
    )
    engram_project_type = st.sidebar.text_input(
        "Engram project type",
        value=engram_options.get("project_type", "programming_assistant"),
        key="engram_project_type_input",
    )
    rag_config = st.sidebar.text_input(
        "RAG config path",
        value=rag_options.get("config", "") or "",
        key="rag_config_input",
    )
    rag_collection = st.sidebar.text_input(
        "RAG collection",
        value=rag_options.get("collection", "default"),
        key="rag_collection_input",
    )
    rag_system_prompt = st.sidebar.text_area(
        "RAG system prompt",
        value=rag_options.get("system_prompt", ""),
        key="rag_system_prompt_input",
    )

    controls = {
        "engine_id": engine_id,
        "model_id": model_id,
        "engine_config": engine_config,
        "engine_settings": {
            "temperature": float(engine_temperature),
            "max_output_tokens": None if int(engine_max_output_tokens) <= 0 else int(engine_max_output_tokens),
        },
        "augmenter_ids": augmenter_ids,
        "max_prompt_tokens": None if int(max_prompt_tokens) <= 0 else int(max_prompt_tokens),
        "reserve_output_tokens": int(reserve_output_tokens),
        "augmenter_options": {
            "baseline": {
                "system_prompt": system_prompt,
            },
            "engram": {
                "base_dir": engram_base_dir,
                "project_id": engram_project_id,
                "project_type": engram_project_type,
            },
            "rag": {
                "config": rag_config or None,
                "collection": rag_collection,
                "system_prompt": rag_system_prompt,
            },
        },
    }

    run_readiness = engine_service.get_run_readiness(
        engine_id=controls["engine_id"],
        config=controls["engine_config"],
        model_id=controls["model_id"],
    )
    controls["run_readiness"] = run_readiness
    controls["submission_readiness"] = compute_submission_readiness(
        controls,
        engine_service=engine_service,
        augmenter_service=augmenter_service,
    )

    st.session_state.current_controls = controls
    return controls

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

def render_transcript():
    store: SessionStore = st.session_state.session_store
    turns = store.list_turns(st.session_state.current_session_id)

    st.subheader("Transcript")
    if not turns:
        st.caption("No turns yet.")
        return

    for turn in turns:
        with st.chat_message(turn.role):
            st.markdown(turn.text)
            meta = turn.meta or {}
            if meta:
                with st.expander("Turn meta", expanded=False):
                    st.json(meta)




def _render_agent_execution_status(trace, *, include_json: bool = False) -> None:
    import streamlit as st

    exec_summary = get_agent_execution_summary(trace)
    rows = get_agent_execution_rows(trace)
    if not rows:
        return
    st.markdown("**Execution status**")
    c1, c2, c3 = st.columns(3)
    c1.metric("Blocked", int(exec_summary.get("blocked_count", 0)))
    c2.metric("Degraded", int(exec_summary.get("degraded_count", 0)))
    c3.metric("Approval", int(exec_summary.get("approval_count", 0)))
    st.dataframe(rows, use_container_width=True)
    if include_json:
        with st.expander("Execution status JSON", expanded=False):
            st.json(exec_summary)

def render_single_run_panel(runs):
    st.subheader("Inspector")
    if not runs:
        st.caption("No runs yet.")
        return

    run_labels = [
        f"{run.created_at.isoformat(timespec='seconds')} | {run.augmenter_id} | {run.engine_id}"
        for run in runs
    ]
    selected_label = st.selectbox("Select run", options=run_labels, index=0, key="single_run_select")
    selected_run = runs[run_labels.index(selected_label)]
    st.caption(f"status={selected_run.status}")

    tabs = st.tabs(
        ["Response", "Prompt", "Sections", "Token accounting", "Evidence", "Retrieval", "Agent", "Signals", "Metrics", "Events", "Raw JSON"]
    )

    with tabs[0]:
        if selected_run.status == "skipped":
            st.warning(selected_run.error or "Branch was skipped.")
        elif selected_run.error:
            st.error(selected_run.error)
        else:
            st.write(selected_run.response_text)

    with tabs[1]:
        st.code(get_final_prompt(selected_run.trace, fallback=selected_run.prompt or ""), language="markdown")

    with tabs[2]:
        sections = get_sections(selected_run.trace)
        if not sections:
            st.caption("No trace sections.")
        else:
            for section in sections:
                title = section.get("title", "Section")
                origin = section.get("origin", "")
                with st.expander(f"{title} [{origin}]", expanded=(origin != "prompt")):
                    st.write(section.get("text", ""))

    with tabs[3]:
        st.json(get_token_accounting(selected_run.trace))

    with tabs[4]:
        evidence = get_evidence(selected_run.trace)
        if not evidence:
            st.caption("No evidence.")
        else:
            for item in evidence:
                st.markdown(f"**{item.get('source', '')}**")
                st.write(item.get("text", ""))
                score = item.get("score")
                if score is not None:
                    st.caption(f"score={score}")

    with tabs[5]:
        summary = get_retrieval_summary(selected_run.trace)
        events = get_retrieval_events(selected_run.trace)
        if summary:
            st.json(summary)
        if events:
            st.dataframe(events, use_container_width=True)
        elif not summary:
            st.caption("No retrieval diagnostics.")

    with tabs[6]:
        summary = get_agent_summary(selected_run.trace)
        exec_summary = get_agent_execution_summary(selected_run.trace)
        rows = get_agent_execution_rows(selected_run.trace)
        events = get_agent_events(selected_run.trace)
        if summary:
            st.json(summary)
        if rows:
            _render_agent_execution_status(selected_run.trace, include_json=True)
        if events:
            st.dataframe(events, use_container_width=True)
        elif not summary and not rows:
            st.caption("No agent diagnostics.")

    with tabs[7]:
        _render_agent_execution_status(selected_run.trace, include_json=True)
        st.json(get_signals(selected_run.trace))

    with tabs[8]:
        st.json(get_metrics(selected_run.trace))

    with tabs[9]:
        _render_agent_execution_status(selected_run.trace, include_json=False)
        events = get_events(selected_run.trace)
        if not events:
            st.caption("No events.")
        else:
            st.dataframe(events, use_container_width=True)

    with tabs[10]:
        _render_agent_execution_status(selected_run.trace, include_json=True)
        st.code(json.dumps(_safe_jsonable(selected_run.trace), indent=2, ensure_ascii=False), language="json")


def render_inspector_area():
    store: SessionStore = st.session_state.session_store
    runs = store.list_runs(st.session_state.current_session_id)
    controls = st.session_state.current_controls

    single_tab, compare_tab, models_tab, startup_tab = st.tabs(["Single run", "Compare", "Models", "Startup"])
    with single_tab:
        render_single_run_panel(runs)
    with compare_tab:
        render_compare_panel(
            runs,
            inspector_service=st.session_state.inspector_service,
            beginner_mode=bool(st.session_state.get("ui_beginner_mode", True)),
        )
    with models_tab:
        render_models_panel(st.session_state.engine_service)
    with startup_tab:
        render_startup_panel(
            st.session_state.engine_service,
            selected_engine_id=controls["engine_id"],
            selected_engine_config=controls.get("engine_config", {}),
            augmenter_service=st.session_state.augmenter_service,
            inspector_service=st.session_state.inspector_service,
            selected_augmenter_ids=list(controls.get("augmenter_ids", [])),
            augmenter_options=dict(controls.get("augmenter_options", {})),
            beginner_mode=bool(st.session_state.get("ui_beginner_mode", True)),
        )

def render_engine_config_controls(engine_service, engine_id: str, existing_config: dict[str, object] | None) -> dict[str, object]:
    schema = engine_service.get_engine_config_schema(engine_id)
    if not schema:
        return {}

    st.sidebar.markdown("**Engine connection**")
    config: dict[str, object] = {}
    current = dict(existing_config or {})

    for field in schema:
        key = f"engine_cfg_{engine_id}_{field.name}"
        default_value = current.get(field.name, field.default)

        if field.field_type == "bool":
            value = st.sidebar.checkbox(
                field.label,
                value=bool(default_value),
                help=field.help or None,
                key=key,
            )
        elif field.field_type == "int":
            value = st.sidebar.number_input(
                field.label,
                value=int(default_value or 0),
                step=1,
                help=field.help or None,
                key=key,
            )
        elif field.field_type == "float":
            value = st.sidebar.number_input(
                field.label,
                value=float(default_value or 0.0),
                step=0.1,
                help=field.help or None,
                key=key,
            )
        elif field.field_type == "password":
            value = st.sidebar.text_input(
                field.label,
                value=str(default_value or ""),
                type="password",
                help=field.help or None,
                placeholder=field.placeholder or None,
                key=key,
            )
        else:
            value = st.sidebar.text_input(
                field.label,
                value=str(default_value or ""),
                help=field.help or None,
                placeholder=field.placeholder or None,
                key=key,
            )

        if field.field_type == "text" and value == "":
            continue
        config[field.name] = value

    return config

def _safe_jsonable(value):
    try:
        json.dumps(value)
        return value
    except Exception:
        return str(value)

def compute_submission_readiness(controls: dict[str, object], engine_service, augmenter_service) -> dict[str, object]:
    engine_readiness = controls["run_readiness"]
    augmenter_ids = list(controls["augmenter_ids"])
    augmenter_options = dict(controls.get("augmenter_options", {}))

    branch_readiness = [
        augmenter_service.get_augmenter_readiness(
            augmenter_id,
            options=augmenter_options.get(augmenter_id, {}),
        )
        for augmenter_id in augmenter_ids
    ]

    if not engine_readiness.can_run:
        return {
            "can_submit": False,
            "severity": engine_readiness.severity,
            "message": engine_readiness.message,
            "engine_readiness": engine_readiness,
            "branch_readiness": branch_readiness,
        }

    runnable_branches = [r for r in branch_readiness if r.can_run]
    if not runnable_branches:
        return {
            "can_submit": False,
            "severity": "error",
            "message": "No selected augmenter branches are runnable.",
            "engine_readiness": engine_readiness,
            "branch_readiness": branch_readiness,
        }

    skipped = [r for r in branch_readiness if not r.can_run]
    if skipped:
        return {
            "can_submit": True,
            "severity": "warning",
            "message": f"{len(skipped)} branch(es) will be skipped; {len(runnable_branches)} branch(es) will run.",
            "engine_readiness": engine_readiness,
            "branch_readiness": branch_readiness,
        }

    return {
        "can_submit": True,
        "severity": "ok",
        "message": "All selected branches are runnable.",
        "engine_readiness": engine_readiness,
        "branch_readiness": branch_readiness,
    }


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


def main():
    st.set_page_config(page_title="LLM Inspector UI", layout="wide")
    st.title("LLM Inspector UI")

    init_services()
    ensure_current_session()
    controls = sidebar_controls()

    left, right = st.columns([1.1, 0.9])

    with left:
        render_run_readiness_banner(controls["run_readiness"])
        render_submission_readiness_banner(controls["submission_readiness"])
        render_transcript()
        submit_input(controls)

    with right:
        render_inspector_area()


if __name__ == "__main__":
    main()
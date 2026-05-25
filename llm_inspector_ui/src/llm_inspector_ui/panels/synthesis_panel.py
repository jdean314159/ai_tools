"""Synthesis panel for llm_inspector_ui.

Three tabs:
  Rules    — searchable table of stored procedural rules
  Relations — table of DERIVED_FROM / RELATES_TO edges
  Run       — form to trigger synthesize_now() on demand

Degrades gracefully when:
  - Engram is not installed (shows install message)
  - The augmenter has no synthesis layer
  - No rules have been synthesised yet (prompts user to run synthesis)

Author: Jeffrey Dean
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_pm(base_dir: Path, project_id: str, project_type: str = "programming_assistant"):
    """Return a ProjectMemory instance, or None on import failure."""
    try:
        from engram.project_memory import ProjectMemory
        try:
            from engram import ProjectType
        except Exception:
            from engram.project_memory import ProjectType
        return ProjectMemory(
            project_id=project_id,
            project_type=ProjectType(project_type),
            base_dir=base_dir,
            llm_engine=None,
        )
    except Exception:
        return None


def _has_synthesis(pm) -> bool:
    """True when pm has the synthesis API."""
    return (
        pm is not None
        and hasattr(pm, "synthesize_now")
        and hasattr(pm, "audit_memory")
        and pm.semantic is not None
        and hasattr(pm.semantic, "search_synthesis_rules")
    )


def _list_all_rules(pm, project_id: str, limit: int = 200) -> list[dict[str, Any]]:
    """Fetch up to `limit` rules via a broad search (most-common words)."""
    # FTS5 needs a query — use common English words to pull all docs
    # then deduplicate by id.
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for term in ("the", "a", "when", "use", "set", "run", "do", "all", "any"):
        try:
            hits = pm.semantic.search_synthesis_rules(
                term, project_id=project_id, limit=limit
            )
            for h in hits:
                if h["id"] not in seen:
                    seen.add(h["id"])
                    rows.append(h)
        except Exception:
            pass
        if len(rows) >= limit:
            break
    return rows[:limit]


# ---------------------------------------------------------------------------
# Panel renderer
# ---------------------------------------------------------------------------

def render_synthesis_panel(
    augmenter_service: Any,
    *,
    beginner_mode: bool = False,
) -> None:
    import streamlit as st

    st.header("Procedural Memory — Synthesis")

    # --- Availability check -------------------------------------------
    try:
        import engram  # noqa: F401
    except ImportError:
        st.warning(
            "Engram is not installed. Install it with `pip install -e .` "
            "from the `engram/` directory."
        )
        return

    base_dir = Path(augmenter_service.engram_base_dir)
    project_id = augmenter_service.engram_project_id
    project_type = getattr(augmenter_service, "engram_project_type", "programming_assistant")

    pm = _get_pm(base_dir, project_id, project_type)

    if pm is None:
        st.error("Could not initialise ProjectMemory. Check the base directory in sidebar.")
        return

    if not _has_synthesis(pm):
        st.info(
            "Synthesis layer is not available for this augmenter. "
            "Switch to the **engram** augmenter to use procedural memory."
        )
        pm.close()
        return

    if beginner_mode:
        st.caption(
            "**Procedural memory** stores generalisable rules extracted from past sessions — "
            "patterns like 'when X, do Y' that apply across many conversations. "
            "Rules are built by running Synthesis, which uses a local LLM to analyse "
            "recent episodes and extract reusable knowledge."
        )

    rules_tab, relations_tab, run_tab = st.tabs(["Rules", "Relations", "Run Synthesis"])

    # ------------------------------------------------------------------ Rules
    with rules_tab:
        _render_rules_tab(pm, project_id, beginner_mode)

    # -------------------------------------------------------------- Relations
    with relations_tab:
        _render_relations_tab(pm, project_id)

    # ----------------------------------------------------------- Run synthesis
    with run_tab:
        _render_run_tab(pm, project_id)

    pm.close()


# ---------------------------------------------------------------------------
# Tab renderers
# ---------------------------------------------------------------------------

def _render_rules_tab(pm, project_id: str, beginner_mode: bool) -> None:
    import streamlit as st

    n_rules = pm.semantic.count_synthesis_rules(project_id=project_id)

    if n_rules == 0:
        st.info(
            "No synthesis rules found for this project. "
            "Go to the **Run Synthesis** tab to extract rules from recent episodes."
        )
        return

    st.caption(f"{n_rules} rule(s) stored for project `{project_id}`")

    query = st.text_input(
        "Search rules",
        placeholder="e.g. SQLite, async, test, WAL",
        key="synthesis_rule_search",
    )

    if query.strip():
        try:
            rows = pm.semantic.search_synthesis_rules(
                query.strip(), project_id=project_id, limit=50
            )
        except Exception as exc:
            st.error(f"Search failed: {exc}")
            rows = []
    else:
        rows = _list_all_rules(pm, project_id, limit=100)

    if not rows:
        st.warning("No rules matched. Try a different search term.")
        return

    # Render as a simple table
    import pandas as pd
    df = pd.DataFrame([
        {
            "Rule": r.get("rule_text", ""),
            "Confidence": round(float(r.get("confidence", 0)), 2),
            "Support": int(r.get("support_count", 0)),
            "Last validated": _fmt_ts(r.get("last_validated")),
            "ID": r.get("id", ""),
        }
        for r in rows
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    if beginner_mode:
        st.caption(
            "**Confidence** — how clearly this rule was established by the supporting episodes (0–1). "
            "**Support** — number of distinct episodes that evidence this rule."
        )


def _render_relations_tab(pm, project_id: str) -> None:
    import streamlit as st

    st.caption("Typed edges linking rules to supporting episodes.")

    try:
        # Fetch all DERIVED_FROM relations for this project
        from_rows = pm.semantic.get_relations_for(
            relation_type="DERIVED_FROM", project_id=project_id, limit=200
        )
        other_rows = [
            r for rel_type in ("RELATES_TO", "SUPERSEDES", "GENERALIZES", "APPLIES_TO")
            for r in pm.semantic.get_relations_for(
                relation_type=rel_type, project_id=project_id, limit=50
            )
        ]
        all_rows = from_rows + other_rows
    except Exception as exc:
        st.error(f"Could not load relations: {exc}")
        return

    if not all_rows:
        st.info("No relations stored yet. Relations are created automatically when synthesis runs.")
        return

    import pandas as pd
    df = pd.DataFrame([
        {
            "Type": r.get("relation_type", ""),
            "Subject": r.get("subject_id", "")[:24] + "…" if len(r.get("subject_id","")) > 24 else r.get("subject_id",""),
            "Object": r.get("object_id", "")[:24] + "…" if len(r.get("object_id","")) > 24 else r.get("object_id",""),
            "Weight": round(float(r.get("weight", 0)), 2),
            "Created": _fmt_ts(r.get("created_at")),
        }
        for r in all_rows
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(
        f"{len(all_rows)} relation(s). DERIVED_FROM links rules to their supporting episodes."
    )


def _render_run_tab(pm, project_id: str) -> None:
    import streamlit as st

    st.subheader("Run Synthesis Now")
    st.caption(
        "Analyses recent episodes and extracts generalizable rules using a local LLM. "
        "Requires the `synthesis` or `tier2_cognitive` engine configured in `llm_engines.yaml`."
    )

    col1, col2 = st.columns(2)
    with col1:
        window_size = st.number_input(
            "Episode window", min_value=5, max_value=500, value=50, step=5,
            help="Number of recent episodes to include in the synthesis pass.",
            key="synth_window_size",
        )
        days_back = st.number_input(
            "Days back", min_value=1, max_value=365, value=30, step=1,
            help="How far back in time to fetch episodes.",
            key="synth_days_back",
        )
    with col2:
        min_support = st.number_input(
            "Min support", min_value=1, max_value=20, value=3, step=1,
            help="Minimum episodes that must support a rule for it to be stored.",
            key="synth_min_support",
        )
        min_confidence = st.slider(
            "Min confidence", min_value=0.0, max_value=1.0, value=0.60, step=0.05,
            help="Rules with lower confidence are discarded.",
            key="synth_min_confidence",
        )

    if st.button("▶ Run Synthesis", type="primary", key="synth_run_btn"):
        with st.spinner("Running synthesis… this may take 5–30 seconds."):
            try:
                result = pm.synthesize_now(
                    window_size=int(window_size),
                    days_back=int(days_back),
                    min_support=int(min_support),
                    min_confidence=float(min_confidence),
                )
            except Exception as exc:
                st.error(f"Synthesis failed: {exc}")
                return

        if result.get("skipped_reason"):
            st.warning(f"Synthesis skipped: `{result['skipped_reason']}`")
        else:
            st.success(
                f"Done — {result['rules_written']} new rule(s), "
                f"{result['rules_skipped']} already known, "
                f"{result['relations_written']} relation(s), "
                f"from {result['window_size']} episodes "
                f"in {result['extraction_seconds']:.1f}s."
            )
            if result["rules_written"] > 0:
                st.info("Switch to the **Rules** tab to inspect the new rules.")

        with st.expander("Full result"):
            st.json(result)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _fmt_ts(ts: Optional[float]) -> str:
    if ts is None:
        return "—"
    import datetime
    try:
        return datetime.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "—"

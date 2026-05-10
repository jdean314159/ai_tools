"""Prompt builder — core build_prompt logic extracted from ProjectMemory.

build_prompt_core() and build_prompt_trace_core() accept a ProjectMemory
instance as their first argument (pm). ProjectMemory.build_prompt() and
build_prompt_trace() are thin wrappers that delegate here.

Author: Jeffrey Dean
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .helpers import (
    _MEMORY_WRAPPER_PREAMBLE,
    _MEMORY_WRAPPER_BEGIN,
    _MEMORY_WRAPPER_END,
    wrap_memory_block,
    assemble_prompt,
    truncate_to_tokens,
    _canonical_subject_for_prompt,
    _canonical_value_for_prompt,
    _canonical_sentence_for_prompt,
    _prompt_friendly_episodic_text,
    _prompt_friendly_semantic_row,
    _CORRECTION_USE_INSTEAD_PROMPT,
    _SCHEDULE_UPDATE_PROMPT,
    _REGION_UPDATE_PROMPT,
    _KEEP_IN_NOT_PROMPT,
    _PREFIX_ONLY_PROMPT,
)

if TYPE_CHECKING:
    from ..project_memory import ProjectMemory


def _get_helper_map():
    """Lazy helper map — only built when semantic helpers are needed."""
    from .memory.semantic_memory import ProjectType
    from .memory.semantic_helpers import (
        ProgrammingAssistantHelpers,
        FileOrganizerHelpers,
        LanguageTutorHelpers,
        VoiceInterfaceHelpers,
    )
    return {
        ProjectType.PROGRAMMING_ASSISTANT: ProgrammingAssistantHelpers,
        ProjectType.FILE_ORGANIZER: FileOrganizerHelpers,
        ProjectType.LANGUAGE_TUTOR: LanguageTutorHelpers,
        ProjectType.VOICE_INTERFACE: VoiceInterfaceHelpers,
    }


def hierarchical_compress_text(
    sections,
    neural_hint: str,
    available_tokens: int,
    count_fn,
) -> str:
    """Compress memory content using layer priority to stay within available_tokens.

    Compression order (most expendable first):
      1. Drop cold storage
      2. Drop neural hint
      3. Truncate episodic (retrieved excerpts, most compressible)
      4. Truncate working memory (keep most recent turns)
      5. Semantic is non-evictable: drop everything else before touching it

    Replaces the flat LLM-compress-or-truncate approach with one that
    respects the information hierarchy from the V2 design.
    """
    def _assemble(parts, hint=""):
        memory_parts = []
        for key in ("working", "episodic", "semantic", "cold"):
            val = parts.get(key, "")
            if val:
                memory_parts.append(f"[{key.upper()}]\n{val}")
        if hint:
            memory_parts.append(f"[NEURAL CONTEXT]\n{hint}")
        return "\n\n".join(memory_parts).strip()

    current = dict(sections)
    hint = neural_hint

    content = _assemble(current, hint)
    if count_fn(content) <= available_tokens:
        return content

    # Phase 1: Drop cold storage (lowest retrieval priority)
    if current.get("cold"):
        current["cold"] = ""
        content = _assemble(current, hint)
        logger.debug("Hierarchical compress phase 1: dropped cold storage")
        if count_fn(content) <= available_tokens:
            return content

    # Phase 1b: Drop neural hint (sub-symbolic, least critical under pressure)
    if hint:
        hint = ""
        content = _assemble(current, hint)
        logger.debug("Hierarchical compress phase 1b: dropped neural hint")
        if count_fn(content) <= available_tokens:
            return content

    # Phase 2: Truncate episodic
    if current.get("episodic"):
        sem_tok = count_fn(f"[SEMANTIC]\n{current.get('semantic', '')}") if current.get("semantic") else 0
        work_tok = count_fn(f"[WORKING]\n{current.get('working', '')}") if current.get("working") else 0
        episodic_budget = max(0, available_tokens - sem_tok - work_tok - 50)
        current["episodic"] = truncate_to_tokens(current["episodic"], episodic_budget, count_fn)
        content = _assemble(current, hint)
        logger.debug("Hierarchical compress phase 2: episodic truncated to %d tokens", episodic_budget)
        if count_fn(content) <= available_tokens:
            return content

    # Phase 3: Truncate working memory
    if current.get("working"):
        sem_tok = count_fn(f"[SEMANTIC]\n{current.get('semantic', '')}") if current.get("semantic") else 0
        ep_tok = count_fn(f"[EPISODIC]\n{current.get('episodic', '')}") if current.get("episodic") else 0
        working_budget = max(0, available_tokens - sem_tok - ep_tok - 50)
        current["working"] = truncate_to_tokens(current["working"], working_budget, count_fn)
        content = _assemble(current, hint)
        logger.debug("Hierarchical compress phase 3: working memory truncated to %d tokens", working_budget)
        if count_fn(content) <= available_tokens:
            return content

    # Phase 4 (hard limit): semantic is non-evictable; drop everything else
    semantic_only = current.get("semantic", "")
    logger.warning("Hierarchical compress phase 4: extreme pressure - retaining semantic layer only")
    return f"[SEMANTIC]\n{semantic_only}" if semantic_only else ""


def build_prompt_core(pm,
        user_message: str,
        *,
        query: str | None = None,
        semantic_query: str | None = None,
        max_prompt_tokens: int | None = None,
        reserve_output_tokens: int = 512,
        include_cold_fallback: bool = True,
        store_overflow_summary: bool = False,
        return_trace: bool = False,
):
    """
    Build the final prompt for an LLM call by combining:
    - system prompt
    - memory/retrieval context (working / episodic / semantic / cold)
    - user message

    Returns a dict with at least:
      {
        "prompt": str,
        "context": ContextResult,
        "prompt_tokens": int,
        "memory_tokens": int,
        "compressed": bool,
      }

    If return_trace=True, also includes:
      {
        "trace": PromptBuildTrace
      }
    """
    import logging

    logger = logging.getLogger(__name__)

    # -----------------------------
    # Resolve query and token budget
    # -----------------------------
    resolved_query = query or user_message

    total_budget = max_prompt_tokens if max_prompt_tokens is not None else getattr(
        pm.budget, "total_prompt_tokens", None
    )
    if total_budget is None:
        total_budget = 4096

    available_for_prompt = max(1, total_budget - max(0, reserve_output_tokens))

    # -----------------------------
    # Retrieve context
    # -----------------------------
    compressed = False

    context = pm.get_context(
        query=resolved_query,
        max_tokens=total_budget,
        semantic_query=semantic_query,
        cold_fallback=include_cold_fallback,
    )
    retrieval = context

    # Support either object-style or dict-style retrieval result
    working = getattr(context, "working", None)
    episodic = getattr(context, "episodic", None)
    semantic = getattr(context, "semantic", None)
    cold = getattr(context, "cold", None)

    if working is None and isinstance(context, dict):
        working = context.get("working")
        episodic = context.get("episodic")
        semantic = context.get("semantic")
        cold = context.get("cold")

    working = working or []
    episodic = episodic or []
    semantic = semantic or []
    cold = cold or []

    # -----------------------------
    # Build a context result object
    # -----------------------------
    ContextResult = type(context) if not isinstance(context, dict) else None

    def _safe_text(x):
        for attr in ("text", "content", "message", "value"):
            if hasattr(x, attr):
                try:
                    v = getattr(x, attr)
                    if isinstance(v, str) and v.strip():
                        return v
                except Exception:
                    pass
        if isinstance(x, dict):
            for k in ("text", "content", "message", "value"):
                v = x.get(k)
                if isinstance(v, str) and v.strip():
                    return v
        return str(x)

    def _count_items_tokens(items):
        total = 0
        for item in items:
            try:
                total += int(pm._token_counter(_safe_text(item)))
            except Exception:
                total += max(1, len(_safe_text(item).split()))
        return total

    working_tokens = _count_items_tokens(working)
    episodic_tokens = _count_items_tokens(episodic)
    semantic_tokens = _count_items_tokens(semantic)
    cold_tokens = _count_items_tokens(cold)

    if hasattr(context, "working_tokens"):
        context.working_tokens = working_tokens
        context.episodic_tokens = episodic_tokens
        context.semantic_tokens = semantic_tokens
        context.cold_tokens = cold_tokens
    else:
        context = {
            "working": working,
            "episodic": episodic,
            "semantic": semantic,
            "cold": cold,
            "working_tokens": working_tokens,
            "episodic_tokens": episodic_tokens,
            "semantic_tokens": semantic_tokens,
            "cold_tokens": cold_tokens,
        }

    # -----------------------------
    # Turn context into prompt sections
    # -----------------------------
    system_prompt = getattr(pm, "system_prompt", "") or ""

    sections = []

    if system_prompt.strip():
        sections.append(("system", "System", system_prompt))

    def _format_items(items, limit=None):
        if not items:
            return ""
        lines = []
        selected = items if limit is None else items[:limit]
        for i, item in enumerate(selected, start=1):
            lines.append(f"{i}. {_safe_text(item)}")
        if limit is not None and len(items) > limit:
            lines.append(f"... ({len(items) - limit} more)")
        return "\n".join(lines)

    if hasattr(context, "to_prompt_sections"):
        prompt_sections = context.to_prompt_sections()
        working_text = prompt_sections.get("working", "")
        episodic_text = prompt_sections.get("episodic", "")
        semantic_text = prompt_sections.get("semantic", "")
        cold_text = prompt_sections.get("cold", "")
    else:
        working_text = _format_items(working)
        episodic_text = _format_items(episodic)
        semantic_text = _format_items(semantic)
        cold_text = _format_items(cold)

    if working_text:
        sections.append(("working", "Working", working_text))
    if episodic_text:
        sections.append(("episodic", "Episodic", episodic_text))
    if semantic_text:
        sections.append(("semantic", "Semantic", semantic_text))
    if cold_text:
        sections.append(("cold", "Cold", cold_text))

    # --- Synthesis rules block (Option A: capped append) ---
    # Search for rules matching the query, cap at 3 rules / 300 tokens.
    # Runs only when semantic layer is available and has synthesis rules.
    _synthesis_text = pm._build_synthesis_block(
        query=resolved_query,
        max_rules=3,
        max_tokens=300,
    )
    if _synthesis_text:
        sections.append(("synthesis", "Procedural Rules", _synthesis_text))

    sections.append(("user", "User", user_message))

    # -----------------------------
    # Assemble full prompt
    # -----------------------------
    def _render_sections(parts):
        rendered = []
        for _origin, title, text in parts:
            if text.strip():
                rendered.append(f"## {title}\n{text}")
        return "\n\n".join(rendered).strip()

    final_parts = list(sections)
    prompt = _render_sections(final_parts)
    prompt_tokens = int(pm._token_counter(prompt))

    # -----------------------------
    # Pressure valve / truncation
    # -----------------------------
    if prompt_tokens > available_for_prompt:
        compressed = True

        kept = []
        memory_parts = []
        for part in sections:
            if part[0] in ("system", "user"):
                kept.append(part)
            else:
                memory_parts.append(part)

        remaining = []
        for part in memory_parts:
            trial_parts = kept[:-1] + remaining + [part] + [kept[-1]] if kept else remaining + [part]
            trial_prompt = _render_sections(trial_parts)
            trial_tokens = int(pm._token_counter(trial_prompt))
            if trial_tokens <= available_for_prompt:
                remaining.append(part)

        if kept:
            system_parts = [p for p in kept if p[0] == "system"]
            user_parts = [p for p in kept if p[0] == "user"]
            final_parts = system_parts + remaining + user_parts
        else:
            final_parts = remaining

        prompt = _render_sections(final_parts)
        prompt_tokens = int(pm._token_counter(prompt))

        if store_overflow_summary:
            logger.debug(
                "store_overflow_summary requested, but summary storage is not implemented in this build."
            )

    # -----------------------------
    # Memory token count
    # -----------------------------
    memory_tokens = working_tokens + episodic_tokens + semantic_tokens + cold_tokens

    result = {
        "prompt": prompt,
        "context": context,
        "prompt_tokens": prompt_tokens,
        "memory_tokens": memory_tokens,
        "compressed": compressed,
    }

    # Preserve extra retrieval metadata if available
    for key in (
            "episodic_count",
            "semantic_count",
            "graph_count",
            "neural_count",
            "retrieved_items",
            "context_items",
            "memory_hits",
            "trace",
            "retrieval_trace",
    ):
        if isinstance(retrieval, dict) and key in retrieval:
            result[key] = retrieval[key]
        elif hasattr(retrieval, key):
            result[key] = getattr(retrieval, key)

    # -----------------------------
    # Optional inspection trace
    # -----------------------------
    if return_trace:
        try:
            result["trace"] = pm.build_prompt_trace(
                user_message=user_message,
                query=resolved_query,
                semantic_query=semantic_query,
                max_prompt_tokens=max_prompt_tokens,
                reserve_output_tokens=reserve_output_tokens,
                include_cold_fallback=include_cold_fallback,
                store_overflow_summary=store_overflow_summary,
                _result=result,
                _context=context,
                _final_parts=final_parts,
                _available_for_prompt=available_for_prompt,
                _total_budget=total_budget,
                _resolved_query=resolved_query,
            )
        except Exception as e:
            logger.debug("build_prompt_trace failed: %s", e)

    # -----------------------------
    # Telemetry
    # -----------------------------
    try:
        if pm.telemetry is not None and getattr(pm.telemetry, "enabled", False):
            pm.telemetry.emit("build_prompt", {
                "project_id": pm.project_id,
                "session_id": pm.session_id,
                "query": resolved_query,
                "prompt_tokens": prompt_tokens,
                "memory_tokens": memory_tokens,
                "compressed": compressed,
            })
    except Exception as e:
        logger.debug("Telemetry emit failed: %s", e)

    return result


# ------------------------------------------------------------------
# Graph extraction (zero-cost indexing into semantic layer)
# ------------------------------------------------------------------


def build_prompt_trace_core(pm,
        user_message: str,
        *,
        query: str | None = None,
        semantic_query: str | None = None,
        max_prompt_tokens: int | None = None,
        reserve_output_tokens: int = 512,
        include_cold_fallback: bool = True,
        store_overflow_summary: bool = False,
        _result=None,
        _context=None,
        _final_parts=None,
        _available_for_prompt: int | None = None,
        _total_budget: int | None = None,
        _resolved_query: str | None = None,
) -> "PromptBuildTrace":
    from engram.inspection import (
        EvidenceTrace,
        PromptBuildTrace,
        PromptSectionTrace,
        TokenAccountingTrace,
    )

    resolved_query = _resolved_query or query or user_message

    result = _result
    if result is None:
        result = pm.build_prompt(
            user_message=user_message,
            query=resolved_query,
            semantic_query=semantic_query,
            max_prompt_tokens=max_prompt_tokens,
            reserve_output_tokens=reserve_output_tokens,
            include_cold_fallback=include_cold_fallback,
            store_overflow_summary=store_overflow_summary,
            return_trace=False,
        )

    prompt = result.get("prompt", "") or ""
    ctx = _context if _context is not None else result.get("context")
    compressed = bool(result.get("compressed", False))
    prompt_tokens = result.get("prompt_tokens")
    memory_tokens = result.get("memory_tokens")

    total_budget = _total_budget
    if not isinstance(total_budget, int):
        total_budget = max_prompt_tokens if max_prompt_tokens is not None else getattr(
            pm.budget, "total_prompt_tokens", None
        )
        if total_budget is None:
            total_budget = 4096

    available_for_prompt = _available_for_prompt
    if not isinstance(available_for_prompt, int):
        available_for_prompt = max(1, total_budget - max(0, reserve_output_tokens))

    def _ctx_get(name: str, default=None):
        if ctx is None:
            return default
        if isinstance(ctx, dict):
            return ctx.get(name, default)
        return getattr(ctx, name, default)

    def _safe_text(item) -> str:
        for attr in ("text", "content", "message", "value"):
            if hasattr(item, attr):
                try:
                    value = getattr(item, attr)
                    if isinstance(value, str) and value.strip():
                        return value
                except Exception:
                    pass
        if isinstance(item, dict):
            for key in ("text", "content", "message", "value"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        return str(item)

    def _safe_score(item):
        for attr in ("score", "similarity", "weight"):
            if hasattr(item, attr):
                try:
                    value = getattr(item, attr)
                    if isinstance(value, (int, float)):
                        return float(value)
                except Exception:
                    pass
        if isinstance(item, dict):
            for key in ("score", "similarity", "weight"):
                value = item.get(key)
                if isinstance(value, (int, float)):
                    return float(value)
        return None

    def _safe_meta(item, origin: str, text: str, score: float | None) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "origin": origin,
            "text_length": len(text),
        }
        if score is not None:
            meta["score"] = score

        def _copy_if_present(name: str, alias: str | None = None):
            key = alias or name
            if hasattr(item, name):
                try:
                    value = getattr(item, name)
                except Exception:
                    return
                if value is not None and not callable(value):
                    meta[key] = value
            elif isinstance(item, dict):
                value = item.get(name)
                if value is not None:
                    meta[key] = value

        for name, alias in (
            ("record_id", None),
            ("id", None),
            ("kind", None),
            ("created_at", None),
            ("updated_at", None),
            ("timestamp", None),
            ("role", None),
            ("session_id", None),
            ("project_id", None),
            ("source", "source_hint"),
            ("layer", None),
            ("memory_type", None),
            ("canonical", None),
        ):
            _copy_if_present(name, alias)

        if isinstance(item, dict):
            for extra in ("metadata", "meta", "details"):
                value = item.get(extra)
                if isinstance(value, dict):
                    meta[extra] = dict(value)
        else:
            for extra in ("metadata", "meta", "details"):
                if hasattr(item, extra):
                    try:
                        value = getattr(item, extra)
                    except Exception:
                        continue
                    if isinstance(value, dict):
                        meta[extra] = dict(value)

        meta.setdefault("preview", text[:120])
        return meta

    def _count_tokens(text: str) -> int:
        try:
            return int(pm._token_counter(text))
        except Exception:
            return max(1, len(text.split()))

    def _section_token_count(title: str, text: str) -> int:
        return _count_tokens(f"## {title}\n{text}".strip())

    def _parts_from_prompt(rendered_prompt: str):
        title_to_origin = {
            "System": "system",
            "Working": "working",
            "Episodic": "episodic",
            "Semantic": "semantic",
            "Cold": "cold",
            "Procedural Rules": "synthesis",
            "User": "user",
        }
        parts = []
        if not rendered_prompt.strip():
            return parts

        blocks = rendered_prompt.split("\n\n## ")
        for idx, block in enumerate(blocks):
            if idx == 0 and block.startswith("## "):
                block = block[3:]
            title, sep, text = block.partition("\n")
            title = title.strip()
            if not title:
                continue
            origin = title_to_origin.get(title, title.lower().replace(" ", "_"))
            parts.append((origin, title, text if sep else ""))
        return parts

    final_parts = list(_final_parts) if _final_parts is not None else _parts_from_prompt(prompt)

    sections: list[PromptSectionTrace] = []
    per_origin_used: dict[str, int] = {}

    for origin, title, text in final_parts:
        if not isinstance(text, str) or not text.strip():
            continue
        tokens = _section_token_count(title, text)
        per_origin_used[origin] = tokens
        sections.append(
            PromptSectionTrace(
                title=title,
                origin=origin,
                text=text,
                tokens=tokens,
            )
        )

    if prompt.strip():
        sections.append(
            PromptSectionTrace(
                title="Final prompt",
                origin="prompt",
                text=prompt,
                tokens=prompt_tokens if isinstance(prompt_tokens, int) else _count_tokens(prompt),
                meta={"engine": "engram.build_prompt"},
            )
        )

    evidence: list[EvidenceTrace] = []
    seen_evidence: set[tuple[str, str]] = set()

    included_memory_origins = {
        origin for origin, _, _ in final_parts if origin in {"working", "episodic", "semantic", "cold", "synthesis"}
    }

    for origin in ("working", "episodic", "semantic", "cold", "synthesis"):
        if origin not in included_memory_origins:
            continue
        # Synthesis rules come from the prompt block, not from ContextResult layers
        if origin == "synthesis":
            synth_text = pm._build_synthesis_block(resolved_query)
            if synth_text:
                for line in synth_text.splitlines():
                    rule_text = line.lstrip("- ").strip()
                    if rule_text:
                        evidence.append(
                            EvidenceTrace(
                                source="synthesis",
                                text=rule_text,
                                score=None,
                                meta={"origin": "synthesis"},
                            )
                        )
            continue
        items = _ctx_get(origin, []) or []
        for item in items:
            text = _safe_text(item).strip()
            if not text:
                continue
            key = (origin, text)
            if key in seen_evidence:
                continue
            seen_evidence.add(key)
            score = _safe_score(item)
            evidence.append(
                EvidenceTrace(
                    source=origin,
                    text=text,
                    score=score,
                    meta=_safe_meta(item, origin, text, score),
                )
            )

    def _origin_has_content(origin: str) -> bool:
        if origin == "synthesis":
            return bool(pm._build_synthesis_block(resolved_query))
        return bool(_ctx_get(origin, []) or [])

    all_memory_origins = {
        origin for origin in ("working", "episodic", "semantic", "cold", "synthesis")
        if _origin_has_content(origin)
    }
    truncated = bool(all_memory_origins - included_memory_origins)

    token_accounting = TokenAccountingTrace(
        target_tokens=available_for_prompt,
        total_tokens=prompt_tokens if isinstance(prompt_tokens, int) else (
            _count_tokens(prompt) if prompt else None),
        per_origin_budget={},
        per_origin_used=per_origin_used,
        truncated=truncated,
        compressed=compressed,
        notes=[
            f"total_budget={total_budget}",
            f"reserve_output_tokens={reserve_output_tokens}",
            *([f"memory_tokens={memory_tokens}"] if memory_tokens is not None else []),
        ],
    )

    return PromptBuildTrace(
        sections=sections,
        evidence=evidence,
        token_accounting=token_accounting,
        flags={
            "compressed": compressed,
            "truncated": truncated,
            "query": resolved_query,
            "include_cold_fallback": include_cold_fallback,
            "store_overflow_summary": store_overflow_summary,
        },
        final_prompt=prompt,
    )

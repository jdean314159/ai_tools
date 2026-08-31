from __future__ import annotations

from typing import Any, Callable, Optional

from ..inspection import (
    EvidenceTrace,
    PromptBuildTrace,
    PromptSectionTrace,
    TokenAccountingTrace,
)
from ..retrieval.context import ContextResult

TokenCounter = Callable[[str], int]


def _coerce_items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def safe_text(item: Any) -> str:
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


def safe_score(item: Any) -> float | None:
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


def safe_metadata(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        metadata = dict(item.get("metadata") or item.get("meta") or {})
        if item.get("id") and "episode_id" not in metadata:
            metadata["episode_id"] = item["id"]
        return metadata
    metadata = dict(getattr(item, "metadata", None) or getattr(item, "meta", None) or {})
    episode_id = getattr(item, "episode_id", None) or getattr(item, "id", None)
    if episode_id and "episode_id" not in metadata:
        metadata["episode_id"] = episode_id
    return metadata


def count_text_tokens(text: str, token_counter: Optional[TokenCounter] = None) -> int:
    if not text or not text.strip():
        return 0

    if token_counter is not None:
        try:
            return int(token_counter(text))
        except Exception:
            pass

    return max(1, len(text.split()))


def count_items_tokens(
    items: list[Any],
    token_counter: Optional[TokenCounter] = None,
) -> int:
    total = 0
    for item in items:
        total += count_text_tokens(safe_text(item), token_counter=token_counter)
    return total


def normalize_retrieval_result(
    retrieval: Any = None,
    *,
    token_counter: Optional[TokenCounter] = None,
) -> ContextResult:
    if isinstance(retrieval, ContextResult):
        working = _coerce_items(retrieval.working)
        episodic = _coerce_items(retrieval.episodic)
        semantic = _coerce_items(retrieval.semantic)
        cold = _coerce_items(retrieval.cold)
    else:
        working = getattr(retrieval, "working", None)
        episodic = getattr(retrieval, "episodic", None)
        semantic = getattr(retrieval, "semantic", None)
        cold = getattr(retrieval, "cold", None)

        if working is None and isinstance(retrieval, dict):
            working = retrieval.get("working")
            episodic = retrieval.get("episodic")
            semantic = retrieval.get("semantic")
            cold = retrieval.get("cold")

        working = _coerce_items(working)
        episodic = _coerce_items(episodic)
        semantic = _coerce_items(semantic)
        cold = _coerce_items(cold)

    return ContextResult(
        working=working,
        episodic=episodic,
        semantic=semantic,
        cold=cold,
        working_tokens=count_items_tokens(working, token_counter=token_counter),
        episodic_tokens=count_items_tokens(episodic, token_counter=token_counter),
        semantic_tokens=count_items_tokens(semantic, token_counter=token_counter),
        cold_tokens=count_items_tokens(cold, token_counter=token_counter),
    )


def format_items(items: list[Any], *, limit: int = 10) -> str:
    if not items:
        return ""

    lines: list[str] = []
    for i, item in enumerate(items[:limit], start=1):
        lines.append(f"{i}. {safe_text(item)}")

    if len(items) > limit:
        lines.append(f"... ({len(items) - limit} more)")

    return "\n".join(lines)


def render_sections(parts: list[tuple[str, str, str]]) -> str:
    rendered: list[str] = []
    for _origin, title, text in parts:
        if isinstance(text, str) and text.strip():
            rendered.append(f"## {title}\n{text}")
    return "\n\n".join(rendered).strip()


def _parts_from_prompt(rendered_prompt: str) -> list[tuple[str, str, str]]:
    if not rendered_prompt.strip():
        return []

    title_to_origin = {
        "System": "system",
        "Working": "working",
        "Episodic": "episodic",
        "Semantic": "semantic",
        "Cold": "cold",
        "User": "user",
    }

    parts: list[tuple[str, str, str]] = []
    blocks = rendered_prompt.split("\n\n## ")

    for index, block in enumerate(blocks):
        if index == 0 and block.startswith("## "):
            block = block[3:]

        title, sep, text = block.partition("\n")
        title = title.strip()
        if not title:
            continue

        origin = title_to_origin.get(title, title.lower().replace(" ", "_"))
        parts.append((origin, title, text if sep else ""))

    return parts


def build_prompt_trace_from_result(
    *,
    user_message: str,
    result: dict[str, Any],
    system_prompt: str = "",
    query: str | None = None,
    max_prompt_tokens: int | None = None,
    total_prompt_tokens: int | None = None,
    reserve_output_tokens: int = 512,
    include_cold_fallback: bool = True,
    store_overflow_summary: bool = False,
    final_parts: Optional[list[tuple[str, str, str]]] = None,
    token_counter: Optional[TokenCounter] = None,
) -> PromptBuildTrace:
    resolved_query = query or user_message
    prompt = result.get("prompt", "") or ""
    compressed = bool(result.get("compressed", False))
    prompt_tokens = result.get("prompt_tokens")
    memory_tokens = result.get("memory_tokens")

    ctx = result.get("context")
    if not isinstance(ctx, ContextResult):
        ctx = normalize_retrieval_result(ctx, token_counter=token_counter)

    total_budget = total_prompt_tokens if total_prompt_tokens is not None else max_prompt_tokens
    if total_budget is None:
        total_budget = 4096

    available_for_prompt = max(1, total_budget - max(0, reserve_output_tokens))

    parts = list(final_parts) if final_parts is not None else _parts_from_prompt(prompt)

    def section_token_count(title: str, text: str) -> int:
        return count_text_tokens(f"## {title}\n{text}".strip(), token_counter=token_counter)

    sections: list[PromptSectionTrace] = []
    per_origin_used: dict[str, int] = {}

    for origin, title, text in parts:
        if not text.strip():
            continue
        tokens = section_token_count(title, text)
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
                tokens=prompt_tokens
                if isinstance(prompt_tokens, int)
                else count_text_tokens(prompt, token_counter=token_counter),
                meta={"engine": "engram.build_prompt"},
            )
        )

    evidence: list[EvidenceTrace] = []
    seen_evidence: set[tuple[str, str]] = set()

    included_memory_origins = {
        origin for origin, _, _ in parts if origin in {"working", "episodic", "semantic", "cold"}
    }

    for origin in ("working", "episodic", "semantic", "cold"):
        if origin not in included_memory_origins:
            continue

        included_items = result.get("included_items", {})
        items = included_items.get(origin, getattr(ctx, origin, []) or [])
        for item in items:
            text = safe_text(item).strip()
            if not text:
                continue

            key = (origin, text)
            if key in seen_evidence:
                continue

            seen_evidence.add(key)
            evidence.append(
                EvidenceTrace(
                    source=origin,
                    text=text,
                    score=safe_score(item),
                    meta=safe_metadata(item),
                )
            )

    all_memory_origins = {
        origin
        for origin in ("working", "episodic", "semantic", "cold")
        if getattr(ctx, origin, []) or []
    }
    excluded_counts = dict(result.get("budget_diagnostics", {}).get("excluded_item_counts", {}))
    truncated = bool(all_memory_origins - included_memory_origins) or any(excluded_counts.values())

    token_accounting = TokenAccountingTrace(
        target_tokens=available_for_prompt,
        total_tokens=prompt_tokens
        if isinstance(prompt_tokens, int)
        else count_text_tokens(prompt, token_counter=token_counter),
        per_origin_budget={},
        per_origin_used=per_origin_used,
        truncated=truncated,
        compressed=compressed,
        notes=[
            f"total_budget={total_budget}",
            f"reserve_output_tokens={reserve_output_tokens}",
            *([f"memory_tokens={memory_tokens}"] if memory_tokens is not None else []),
            *([f"excluded_items={sum(excluded_counts.values())}"] if excluded_counts else []),
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
            "system_prompt_present": bool(system_prompt.strip()),
            "budget_diagnostics": dict(result.get("budget_diagnostics") or {}),
        },
        final_prompt=prompt,
    )


def build_prompt_from_context(
    *,
    user_message: str,
    context: Any = None,
    retrieval: Any = None,
    system_prompt: str = "",
    query: str | None = None,
    max_prompt_tokens: int | None = None,
    total_prompt_tokens: int | None = None,
    reserve_output_tokens: int = 512,
    include_cold_fallback: bool = True,
    store_overflow_summary: bool = False,
    return_trace: bool = False,
    token_counter: Optional[TokenCounter] = None,
    advisory_hints: Optional[list[Any]] = None,
) -> dict[str, Any]:
    resolved_query = query or user_message

    total_budget = total_prompt_tokens if total_prompt_tokens is not None else max_prompt_tokens
    if total_budget is None:
        total_budget = 4096

    available_for_prompt = max(1, total_budget - max(0, reserve_output_tokens))

    if context is None:
        context_result = normalize_retrieval_result(retrieval, token_counter=token_counter)
    elif isinstance(context, ContextResult):
        context_result = normalize_retrieval_result(context, token_counter=token_counter)
    else:
        context_result = normalize_retrieval_result(context, token_counter=token_counter)

    sections: list[tuple[str, str, str]] = []

    if system_prompt.strip():
        sections.append(("system", "System", system_prompt))

    working_text = format_items(context_result.working)
    episodic_text = format_items(context_result.episodic)
    semantic_text = format_items(context_result.semantic)
    cold_text = format_items(context_result.cold)

    if working_text:
        sections.append(("working", "Working", working_text))
    if episodic_text:
        sections.append(("episodic", "Episodic", episodic_text))
    if semantic_text:
        sections.append(("semantic", "Semantic", semantic_text))
    if cold_text:
        sections.append(("cold", "Cold", cold_text))

    advisory_text = format_items(advisory_hints or [])
    if advisory_text:
        sections.append(("memory_layer", "Memory Layer Hints", advisory_text))

    sections.append(("user", "User", user_message))

    final_parts = list(sections)
    included_items: dict[str, list[Any]] = {
        "working": list(context_result.working),
        "episodic": list(context_result.episodic),
        "semantic": list(context_result.semantic),
        "cold": list(context_result.cold),
        "memory_layer": list(advisory_hints or []),
    }
    prompt = render_sections(final_parts)
    prompt_tokens = count_text_tokens(prompt, token_counter=token_counter)
    compressed = False

    if prompt_tokens > available_for_prompt:
        compressed = True

        system_parts = [part for part in sections if part[0] == "system"]
        user_parts = [part for part in sections if part[0] == "user"]
        memory_parts = [part for part in sections if part[0] not in {"system", "user"}]

        kept_memory: list[tuple[str, str, str]] = []
        included_items = {key: [] for key in included_items}
        origin_titles = {
            "working": "Working",
            "episodic": "Episodic",
            "semantic": "Semantic",
            "cold": "Cold",
            "memory_layer": "Memory Layer Hints",
        }
        origin_items = {
            "working": context_result.working,
            "episodic": context_result.episodic,
            "semantic": context_result.semantic,
            "cold": context_result.cold,
            "memory_layer": list(advisory_hints or []),
        }
        for origin, _title, _text in memory_parts:
            accepted: list[Any] = []
            for item in origin_items.get(origin, []):
                trial_items = accepted + [item]
                trial_part = (origin, origin_titles[origin], format_items(trial_items))
                other_parts = [part for part in kept_memory if part[0] != origin]
                trial_parts = system_parts + other_parts + [trial_part] + user_parts
                if (
                    count_text_tokens(render_sections(trial_parts), token_counter=token_counter)
                    <= available_for_prompt
                ):
                    accepted.append(item)
                else:
                    break
            if accepted:
                included_items[origin] = accepted
                kept_memory.append((origin, origin_titles[origin], format_items(accepted)))

        final_parts = system_parts + kept_memory + user_parts
        prompt = render_sections(final_parts)
        prompt_tokens = count_text_tokens(prompt, token_counter=token_counter)

    advisory_tokens = count_items_tokens(advisory_hints or [], token_counter=token_counter)
    candidate_counts = {
        "working": len(context_result.working),
        "episodic": len(context_result.episodic),
        "semantic": len(context_result.semantic),
        "cold": len(context_result.cold),
        "memory_layer": len(advisory_hints or []),
    }
    included_counts = {key: len(included_items.get(key, [])) for key in candidate_counts}
    excluded_counts = {
        key: candidate_counts[key] - included_counts[key] for key in candidate_counts
    }
    memory_candidate_count = sum(candidate_counts.values())
    memory_included_count = sum(included_counts.values())
    budget_diagnostics = {
        "total_prompt_tokens": total_budget,
        "reserve_output_tokens": max(0, reserve_output_tokens),
        "available_prompt_tokens": available_for_prompt,
        "candidate_item_counts": candidate_counts,
        "included_item_counts": included_counts,
        "excluded_item_counts": excluded_counts,
        "memory_candidate_count": memory_candidate_count,
        "memory_included_count": memory_included_count,
        "memory_starved": memory_candidate_count > 0 and memory_included_count == 0,
    }
    result: dict[str, Any] = {
        "prompt": prompt,
        "context": context_result,
        "prompt_tokens": prompt_tokens,
        "memory_tokens": context_result.memory_tokens() + advisory_tokens,
        "compressed": compressed,
        "included_items": included_items,
        "budget_diagnostics": budget_diagnostics,
    }
    if advisory_hints:
        result["advisory_hints"] = list(advisory_hints)

    if return_trace:
        result["trace"] = build_prompt_trace_from_result(
            user_message=user_message,
            result=result,
            system_prompt=system_prompt,
            query=resolved_query,
            max_prompt_tokens=max_prompt_tokens,
            total_prompt_tokens=total_budget,
            reserve_output_tokens=reserve_output_tokens,
            include_cold_fallback=include_cold_fallback,
            store_overflow_summary=store_overflow_summary,
            final_parts=final_parts,
            token_counter=token_counter,
        )

    return result


__all__ = [
    "build_prompt_from_context",
    "build_prompt_trace_from_result",
    "count_items_tokens",
    "count_text_tokens",
    "format_items",
    "normalize_retrieval_result",
    "render_sections",
    "safe_score",
    "safe_metadata",
    "safe_text",
]

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from llm_inspector.core import EvidenceItem, Section, Trace


def _norm_text(s: str, *, limit: int = 120) -> str:
    s = (s or "").strip().replace("\r\n", "\n")
    s = " ".join(s.split())
    return s[:limit]


def _section_key(sec: Section) -> Tuple[str, str]:
    # Stable identity: origin + title
    return (sec.origin, sec.title)


def _evidence_key(ev: EvidenceItem) -> Tuple[str, str]:
    # Stable identity: source + normalized snippet
    return (ev.source, _norm_text(ev.text, limit=160))


@dataclass(frozen=True)
class SectionDelta:
    origin: str
    title: str
    change: str  # "added" | "removed" | "modified" | "unchanged"
    tokens_a: Optional[int] = None
    tokens_b: Optional[int] = None
    text_a: str = ""
    text_b: str = ""


@dataclass(frozen=True)
class EvidenceDelta:
    source: str
    change: str  # "added" | "removed"
    snippet: str


@dataclass(frozen=True)
class TokenDelta:
    origin: str
    used_a: Optional[int]
    used_b: Optional[int]


@dataclass(frozen=True)
class DiffReport:
    name_a: str
    name_b: str
    section_deltas: List[SectionDelta] = field(default_factory=list)
    evidence_deltas: List[EvidenceDelta] = field(default_factory=list)
    token_deltas: List[TokenDelta] = field(default_factory=list)
    flags: Dict[str, Tuple[object, object]] = field(default_factory=dict)  # e.g. compressed/truncated


def diff_traces(a: Trace, b: Trace, *, name_a: str = "A", name_b: str = "B") -> DiffReport:
    # Sections
    map_a = {_section_key(s): s for s in a.context.sections}
    map_b = {_section_key(s): s for s in b.context.sections}
    keys = sorted(set(map_a) | set(map_b))

    section_deltas: List[SectionDelta] = []
    for k in keys:
        sa = map_a.get(k)
        sb = map_b.get(k)
        if sa is None:
            section_deltas.append(
                SectionDelta(origin=sb.origin, title=sb.title, change="added", tokens_b=sb.tokens, text_b=_norm_text(sb.text, limit=240))
            )
        elif sb is None:
            section_deltas.append(
                SectionDelta(origin=sa.origin, title=sa.title, change="removed", tokens_a=sa.tokens, text_a=_norm_text(sa.text, limit=240))
            )
        else:
            ta = _norm_text(sa.text, limit=240)
            tb = _norm_text(sb.text, limit=240)
            change = "unchanged" if (ta == tb and sa.tokens == sb.tokens) else "modified"
            section_deltas.append(
                SectionDelta(
                    origin=sa.origin,
                    title=sa.title,
                    change=change,
                    tokens_a=sa.tokens,
                    tokens_b=sb.tokens,
                    text_a=ta,
                    text_b=tb,
                )
            )

    # Evidence
    ev_a = {_evidence_key(e): e for e in a.context.evidence}
    ev_b = {_evidence_key(e): e for e in b.context.evidence}
    ev_added = sorted(set(ev_b) - set(ev_a))
    ev_removed = sorted(set(ev_a) - set(ev_b))

    evidence_deltas: List[EvidenceDelta] = []
    for k in ev_added:
        src, snip = k
        evidence_deltas.append(EvidenceDelta(source=src, change="added", snippet=snip))
    for k in ev_removed:
        src, snip = k
        evidence_deltas.append(EvidenceDelta(source=src, change="removed", snippet=snip))

    # Token accounting deltas
    used_a = a.context.token_accounting.per_origin_used or {}
    used_b = b.context.token_accounting.per_origin_used or {}
    origins = sorted(set(used_a) | set(used_b))
    token_deltas = [TokenDelta(origin=o, used_a=used_a.get(o), used_b=used_b.get(o)) for o in origins]

    # Flags
    flags = {
        "compressed": (a.context.token_accounting.compressed, b.context.token_accounting.compressed),
        "truncated": (a.context.token_accounting.truncated, b.context.token_accounting.truncated),
        "total_tokens": (a.context.token_accounting.total_tokens, b.context.token_accounting.total_tokens),
        "target_tokens": (a.context.token_accounting.target_tokens, b.context.token_accounting.target_tokens),
    }

    return DiffReport(
        name_a=name_a,
        name_b=name_b,
        section_deltas=section_deltas,
        evidence_deltas=evidence_deltas,
        token_deltas=token_deltas,
        flags=flags,
    )
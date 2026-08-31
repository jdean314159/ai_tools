from __future__ import annotations

import difflib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Pattern


_TOKEN_RE = re.compile(r"[A-Za-z0-9_./-]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "choose",
    "did",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "local",
    "my",
    "now",
    "of",
    "on",
    "or",
    "should",
    "that",
    "the",
    "this",
    "to",
    "use",
    "we",
    "what",
    "when",
    "which",
    "who",
    "why",
    "with",
    "our",
    "your",
}
_CORRECTION_USE_INSTEAD = re.compile(
    r"^\s*(?:correction|update)\s*:\s*(?:for\s+)?(?P<subject>[^,.;:]+?)\s*,\s*"
    r"(?:use|prefer)\s+(?P<new>.+?)\s+(?:locally\s+)?instead of\s+(?P<old>.+?)(?:[.?!]\s*)?$",
    re.IGNORECASE,
)
_SCHEDULE_UPDATE = re.compile(
    r"^\s*(?:update|correction)\s*:\s*(?:the\s+)?(?P<subject>.+?)\s+"
    r"has\s+(?:moved|changed)\s+to\s+(?P<new>.+?)(?:,\s*not\s+(?P<old>.+?))?(?:[.?!]\s*)?$",
    re.IGNORECASE,
)
_REGION_UPDATE = re.compile(
    r"^\s*(?:update|correction)\s*:\s*(?P<subject>.+?)\s+in\s+(?P<new>[A-Za-z0-9:_./-]+)\s*,\s*not\s+(?P<old>[A-Za-z0-9:_./-]+)(?:[.?!]\s*)?$",
    re.IGNORECASE,
)
_KEEP_IN_NOT = re.compile(
    r"^\s*(?:preference|decision)\s*:\s*keep\s+(?P<subject>.+?)\s+in\s+(?P<new>.+?)\s*,\s*not\s+in\s+(?P<old>.+?)(?:[.?!]\s*)?$",
    re.IGNORECASE,
)
_PREFERENCE_PREFIX = re.compile(
    r"^\s*preference\s*:\s*(?P<content>.+?)(?:[.?!]\s*)?$", re.IGNORECASE
)
_DECISION_PREFIX = re.compile(r"^\s*decision\s*:\s*(?P<content>.+?)(?:[.?!]\s*)?$", re.IGNORECASE)
_TOKEN_ALIASES = {
    "documentation": {"documentation", "docs"},
    "docs": {"documentation", "docs"},
    "repository": {"repository", "repo"},
    "repo": {"repository", "repo"},
    "utility": {"utility", "tool", "script"},
    "utilities": {"utility", "tool", "script"},
    "tool": {"utility", "tool", "script"},
    "tools": {"utility", "tool", "script"},
    "script": {"utility", "tool", "script"},
    "scripts": {"utility", "tool", "script"},
    "sandbox": {"sandbox"},
    "sandboxed": {"sandbox"},
    "sandboxing": {"sandbox"},
    "summary": {"summary"},
    "summaries": {"summary"},
}
_PROGRAMMING_LANGUAGES = {
    "python",
    "java",
    "javascript",
    "typescript",
    "rust",
    "go",
    "haskell",
    "c",
    "c++",
    "csharp",
    "java",
}


@dataclass(frozen=True)
class CanonicalizedEpisode:
    text: str
    metadata: dict[str, Any]
    topic_key: str | None = None


@dataclass(frozen=True)
class IngestionDecision:
    should_store_episode: bool
    importance: float
    reasons: tuple[str, ...] = ()
    normalized_text: str = ""


@dataclass
class LightweightIngestionPolicy:
    episode_threshold: float = 0.45
    min_episode_chars: int = 24
    max_episode_chars: int = 1200
    dedup_threshold: float = 0.88
    internal_retrieval_limit: int = 6
    retrieval_min_score: float = 0.16
    auto_ingest_turns: bool = True
    auto_ingest_roles: tuple[str, ...] = ("user",)
    assistant_memory_kinds: tuple[str, ...] = ("session_summary", "decision", "preference")
    ephemeral_patterns: tuple[Pattern[str], ...] = field(
        default_factory=lambda: (
            re.compile(r"\bignore this\b", re.IGNORECASE),
            re.compile(r"\bdo not remember\b", re.IGNORECASE),
            re.compile(r"\bfor this message only\b", re.IGNORECASE),
            re.compile(r"\btemporary note\b", re.IGNORECASE),
            re.compile(r"\bnot for long[- ]term memory\b", re.IGNORECASE),
            re.compile(r"\bephemeral\b", re.IGNORECASE),
            re.compile(r"\btest message\b", re.IGNORECASE),
            re.compile(r"\bmensaje temporal\b", re.IGNORECASE),
            re.compile(r"\bno recuerdes esto\b", re.IGNORECASE),
        )
    )
    memory_terms: tuple[str, ...] = (
        "remember",
        "important",
        "recall this",
        "note that",
        "keep in mind",
        "recuerda",
        "importante",
    )
    profile_terms: tuple[str, ...] = (
        "i prefer",
        "i like",
        "i don't like",
        "my favorite",
        "i am",
        "i use",
        "i work on",
        "we decided",
        "the plan is",
        "prefiero",
        "me gusta",
        "uso",
        "trabajo en",
        "decidimos",
    )
    task_terms: tuple[str, ...] = (
        "bug",
        "issue",
        "decision",
        "resolved",
        "fix",
        "next step",
        "todo",
        "milestone",
        "deadline",
        "regression",
        "refactor",
        "plan",
        "stacktrace",
        "error",
    )

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "LightweightIngestionPolicy":
        configured_roles = config.get("auto_ingest_roles", ("user",))
        if isinstance(configured_roles, str):
            configured_roles = (configured_roles,)
        return cls(
            episode_threshold=float(config.get("episode_threshold", 0.45)),
            min_episode_chars=int(config.get("min_episode_chars", 24)),
            max_episode_chars=int(config.get("max_episode_chars", 1200)),
            dedup_threshold=float(config.get("dedup_threshold", 0.88)),
            internal_retrieval_limit=int(config.get("internal_retrieval_limit", 6)),
            retrieval_min_score=float(config.get("retrieval_min_score", 0.16)),
            auto_ingest_turns=bool(config.get("auto_ingest_turns", True)),
            auto_ingest_roles=tuple(
                str(role).strip().lower() for role in configured_roles if str(role).strip()
            ),
        )


def _canonical_subject(text: str) -> str:
    value = re.sub(r"\s+", " ", (text or "").strip(" .,!?:;\n\t"))
    return value[:1].upper() + value[1:] if value else value


def _canonical_value(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip(" .,!?:;\n\t"))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_") or "general"


def _canonical_sentence(text: str) -> str:
    value = re.sub(r"\s+", " ", (text or "").strip(" .,!?:;\n\t"))
    return f"{value[:1].upper() + value[1:] if value else value}." if value else value


def _normalize_token(token: str) -> str:
    token = (token or "").strip().lower()
    if not token:
        return token
    if token in _TOKEN_ALIASES:
        return sorted(_TOKEN_ALIASES[token])[0]
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("s") and len(token) > 4 and token[:-1].isalpha():
        return token[:-1]
    return token


def _expanded_tokens(text: str) -> set[str]:
    raw_tokens = _TOKEN_RE.findall((text or "").lower())
    expanded: set[str] = set()
    for raw in raw_tokens:
        token = _normalize_token(raw)
        if not token:
            continue
        expanded.add(token)
        expanded.update(_TOKEN_ALIASES.get(token, {token}))
    return expanded


def derive_search_terms(text: str, metadata: dict[str, Any] | None = None) -> list[str]:
    payload = dict(metadata or {})
    terms = set(_expanded_tokens(text))
    for extra in payload.get("search_terms") or ():
        terms.update(_expanded_tokens(str(extra)))
    if terms & _PROGRAMMING_LANGUAGES:
        terms.update({"language", "tool", "script"})
    lowered = (text or "").lower()
    if "markdown" in lowered and (
        "repo" in lowered
        or "repository" in lowered
        or "docs" in lowered
        or "documentation" in lowered
    ):
        terms.update({"documentation", "docs", "repo", "repository", "markdown"})
    if "docker" in lowered and "command" in lowered and "execution" in lowered:
        terms.update({"sandbox", "docker", "command", "execution"})
    if "us-" in lowered:
        terms.update({"region", "deployment", "deploy"})
    if "qwen" in lowered:
        terms.update({"model", "summary", "batch"})
    return sorted(term for term in terms if term)


def canonicalize_episode(text: str, metadata: dict[str, Any] | None = None) -> CanonicalizedEpisode:
    payload = dict(metadata or {})
    stripped = str(text or "").strip()
    if not stripped:
        return CanonicalizedEpisode("", payload, None)

    match = _CORRECTION_USE_INSTEAD.match(stripped)
    if match:
        subject = _canonical_subject(match.group("subject"))
        new_value = _canonical_value(match.group("new"))
        old_value = _canonical_value(match.group("old"))
        verb = "prefer" if "prefer" in stripped.lower() else "use"
        local_hint = (
            " locally"
            if " locally instead of " in stripped.lower() and "locally" not in new_value.lower()
            else ""
        )
        topic_key = f"usage::{_slug(subject)}"
        canonical_text = f"For {subject}, {verb} {new_value}{local_hint}."
        return CanonicalizedEpisode(
            text=canonical_text,
            metadata={
                **payload,
                "canonical_update": True,
                "topic_key": topic_key,
                "old_value": old_value,
                "search_terms": derive_search_terms(f"{subject} {new_value} {old_value}", payload),
                "update_type": "correction",
                "kind": payload.get("kind")
                or ("preference" if verb == "prefer" else payload.get("kind")),
            },
            topic_key=topic_key,
        )

    match = _SCHEDULE_UPDATE.match(stripped)
    if match:
        subject = _canonical_subject(match.group("subject"))
        new_value = _canonical_value(match.group("new"))
        old_value = _canonical_value(match.group("old"))
        topic_key = f"schedule::{_slug(subject)}"
        canonical_text = f"{subject} is scheduled for {new_value}."
        return CanonicalizedEpisode(
            text=canonical_text,
            metadata={
                **payload,
                "canonical_update": True,
                "topic_key": topic_key,
                "old_value": old_value,
                "search_terms": derive_search_terms(f"{subject} {new_value} {old_value}", payload),
                "update_type": "schedule_update",
            },
            topic_key=topic_key,
        )

    match = _REGION_UPDATE.match(stripped)
    if match:
        subject = _canonical_subject(match.group("subject"))
        new_value = _canonical_value(match.group("new"))
        old_value = _canonical_value(match.group("old"))
        topic_key = f"deployment::{_slug(subject)}"
        canonical_text = f"{subject} should use {new_value}."
        return CanonicalizedEpisode(
            text=canonical_text,
            metadata={
                **payload,
                "canonical_update": True,
                "topic_key": topic_key,
                "old_value": old_value,
                "search_terms": derive_search_terms(
                    f"{subject} region deployment {new_value} {old_value}", payload
                ),
                "update_type": "region_update",
                "kind": payload.get("kind") or "decision",
            },
            topic_key=topic_key,
        )

    match = _KEEP_IN_NOT.match(stripped)
    if match:
        subject = _canonical_subject(match.group("subject"))
        new_value = _canonical_value(match.group("new"))
        old_value = _canonical_value(match.group("old"))
        topic_key = f"location::{_slug(subject)}"
        canonical_text = f"{subject} should live in {new_value}."
        return CanonicalizedEpisode(
            text=canonical_text,
            metadata={
                **payload,
                "canonical_update": True,
                "topic_key": topic_key,
                "old_value": old_value,
                "search_terms": derive_search_terms(
                    f"{subject} documentation docs repo {new_value} {old_value}", payload
                ),
                "update_type": "location_preference",
                "kind": payload.get("kind")
                or ("preference" if stripped.lower().startswith("preference") else "decision"),
            },
            topic_key=topic_key,
        )

    match = _PREFERENCE_PREFIX.match(stripped)
    if match:
        content = _canonical_sentence(match.group("content"))
        return CanonicalizedEpisode(
            text=content,
            metadata={
                **payload,
                "kind": payload.get("kind") or "preference",
                "search_terms": derive_search_terms(content, payload),
            },
            topic_key=None,
        )

    match = _DECISION_PREFIX.match(stripped)
    if match:
        content = _canonical_sentence(match.group("content"))
        return CanonicalizedEpisode(
            text=content,
            metadata={
                **payload,
                "kind": payload.get("kind") or "decision",
                "search_terms": derive_search_terms(content, payload),
            },
            topic_key=None,
        )

    payload = {**payload, "search_terms": derive_search_terms(stripped, payload)}
    return CanonicalizedEpisode(stripped, payload, None)


def distinctive_terms(text: str) -> set[str]:
    return {token for token in tokenize(text) if len(token) >= 5 and token not in _STOPWORDS}


def normalize_text(text: str) -> str:
    tokens = sorted(tokenize(text))
    if tokens:
        return " ".join(tokens)
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def tokenize(text: str) -> set[str]:
    return _expanded_tokens(text)


def text_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    na = normalize_text(a)
    nb = normalize_text(b)
    if na == nb and na:
        return 1.0
    ta = tokenize(na)
    tb = tokenize(nb)
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / max(1, len(ta | tb))
    ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    return max(jaccard, ratio)


def is_ephemeral(text: str, metadata: dict[str, Any], policy: LightweightIngestionPolicy) -> bool:
    if metadata.get("ephemeral"):
        return True
    if any(pattern.search(text or "") for pattern in policy.ephemeral_patterns):
        return True
    lowered = (text or "").lower()
    return "test" in lowered and "message" in lowered and len(lowered.split()) <= 8


def memory_kind(metadata: dict[str, Any]) -> str:
    return str(metadata.get("kind", metadata.get("type", "")) or "").strip().lower()


def assistant_memory_allowed(metadata: dict[str, Any], policy: LightweightIngestionPolicy) -> bool:
    if bool(metadata.get("allow_assistant_memory")):
        return True
    return memory_kind(metadata) in {kind.lower() for kind in policy.assistant_memory_kinds}


def score_text(
    *,
    text: str,
    role: str,
    metadata: dict[str, Any],
    policy: LightweightIngestionPolicy,
) -> IngestionDecision:
    cleaned = (text or "").strip()
    normalized = normalize_text(cleaned)
    if not cleaned:
        return IngestionDecision(False, 0.0, ("empty_content",), normalized)

    reasons: list[str] = []
    if is_ephemeral(cleaned, metadata, policy):
        return IngestionDecision(False, 0.0, ("ephemeral_signal",), normalized)

    role = str(role or "user").strip().lower()
    typed_kind = memory_kind(metadata)
    explicit_importance = metadata.get("importance", 0.0)

    if role == "assistant" and not assistant_memory_allowed(metadata, policy):
        return IngestionDecision(
            False,
            max(0.0, min(1.0, float(explicit_importance or 0.0))),
            ("assistant_turn_filtered",),
            normalized,
        )

    score = 0.05
    lowered = cleaned.lower()

    if metadata.get("remember") or float(explicit_importance or 0.0) >= 0.8:
        score += 0.55
        reasons.append("explicit_memory_signal")

    if any(term in lowered for term in policy.memory_terms):
        score += 0.42
        reasons.append("memory_language")

    if any(term in lowered for term in policy.profile_terms):
        score += 0.22
        reasons.append("profile_signal")

    if any(term in lowered for term in policy.task_terms):
        score += 0.16
        reasons.append("task_signal")

    words = len(cleaned.split())
    score += min(0.12, words / 200.0)
    if words >= 20:
        reasons.append("substantive_turn")

    if typed_kind in {"session_summary", "decision", "preference"}:
        score += 0.42
        reasons.append("typed_memory_signal")

    if metadata.get("canonical_update"):
        score += 0.42
        reasons.append("canonical_update_signal")

    importance = max(float(explicit_importance or 0.0), min(1.0, score))
    should_store = (
        importance >= policy.episode_threshold and len(cleaned) >= policy.min_episode_chars
    )
    return IngestionDecision(should_store, importance, tuple(reasons), normalized)


def score_episode_match(
    *,
    query: str,
    text: str,
    importance: float,
    created_at: float | None,
    metadata: dict[str, Any] | None = None,
) -> float:
    query = (query or "").strip()
    normalized_query = normalize_text(query)
    normalized_text = normalize_text(text)

    metadata = dict(metadata or {})
    q_tokens = tokenize(normalized_query)
    t_tokens = tokenize(normalized_text)
    metadata_tokens = {str(token).lower() for token in metadata.get("search_terms") or ()}

    lexical = 0.0
    if normalized_query:
        if normalized_query and normalized_query in normalized_text:
            lexical = 1.0
        else:
            if q_tokens and t_tokens:
                lexical = len(q_tokens & t_tokens) / max(1, len(q_tokens))
            if q_tokens and metadata_tokens:
                lexical = max(lexical, len(q_tokens & metadata_tokens) / max(1, len(q_tokens)))

    now = time.time()
    recency = 0.0
    if created_at:
        age_days = max(0.0, (now - float(created_at)) / 86400.0)
        recency = max(0.0, 1.0 - min(age_days / 30.0, 1.0))

    specificity_bonus = 0.0
    specificity_penalty = 0.0
    if normalized_query and q_tokens:
        distinctive_query = distinctive_terms(normalized_query)
        overlap = distinctive_query & (t_tokens | metadata_tokens)
        if distinctive_query:
            specificity_bonus = len(overlap) / max(1, len(distinctive_query))
            if not overlap:
                specificity_penalty = 0.18

    if normalized_query:
        score = (
            0.46 * lexical
            + 0.24 * max(0.0, min(1.0, float(importance)))
            + 0.12 * recency
            + 0.24 * specificity_bonus
            - specificity_penalty
        )
    else:
        score = 0.7 * max(0.0, min(1.0, float(importance))) + 0.3 * recency
    return max(0.0, min(1.0, score))


def dedupe_ranked_rows(
    rows: Iterable[dict[str, Any]],
    *,
    limit: int,
    dedup_threshold: float,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        text = str(row.get("text", ""))
        if not text.strip():
            continue
        if any(
            text_similarity(text, str(existing.get("text", ""))) >= dedup_threshold
            for existing in selected
        ):
            continue
        selected.append(row)
        if len(selected) >= int(limit):
            break
    return selected


__all__ = [
    "CanonicalizedEpisode",
    "canonicalize_episode",
    "distinctive_terms",
    "IngestionDecision",
    "LightweightIngestionPolicy",
    "assistant_memory_allowed",
    "dedupe_ranked_rows",
    "is_ephemeral",
    "memory_kind",
    "normalize_text",
    "score_episode_match",
    "score_text",
    "text_similarity",
    "tokenize",
]

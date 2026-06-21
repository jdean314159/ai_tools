from __future__ import annotations


DEFAULT_SEPARATOR = ", "


def normalize_title(value: str) -> str:
    cleaned = value.strip().replace("_", " ")
    if not cleaned:
        return "Untitled"
    return cleaned.title()


def join_labels(labels: list[str], separator: str = DEFAULT_SEPARATOR) -> str:
    cleaned = []
    for label in labels:
        normalized = label.strip()
        if normalized:
            cleaned.append(normalized)
    return separator.join(cleaned)


def score_bucket(score: int) -> str:
    if score < 0:
        return "invalid"
    if score <= 59:
        return "low"
    if score >= 60 and score <= 89:
        return "medium"
    if score >= 90:
        return "high"
    return "invalid"

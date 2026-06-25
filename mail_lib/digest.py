"""Render a deterministic CLI digest for MAIL-00 v0."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .thunderbird import MailMessage
from .triage import Priority, TriageResult


@dataclass(frozen=True)
class DigestItem:
    message: MailMessage
    triage: TriageResult


SECTION_ORDER = [
    (Priority.URGENT, "Urgent"),
    (Priority.NORMAL, "Normal"),
    (Priority.LOW, "Suggested ignores"),
    (Priority.IGNORE, "Suggested ignores"),
]


def build_digest_items(
    messages: Iterable[MailMessage],
    results: Iterable[TriageResult],
) -> list[DigestItem]:
    by_id = {message.header_message_id: message for message in messages}
    items = []
    for result in results:
        message = by_id.get(result.header_message_id)
        if message is not None:
            items.append(DigestItem(message=message, triage=result))
    return items


def render_digest(messages: Iterable[MailMessage], results: Iterable[TriageResult]) -> str:
    items = build_digest_items(messages, results)
    by_priority: dict[Priority, list[DigestItem]] = defaultdict(list)
    for item in items:
        by_priority[item.triage.priority].append(item)

    lines = ["MAIL-00 Digest", ""]
    emitted_ignore = False
    for priority, title in SECTION_ORDER:
        if title == "Suggested ignores" and emitted_ignore:
            continue
        if title == "Suggested ignores":
            section_items = by_priority[Priority.LOW] + by_priority[Priority.IGNORE]
            emitted_ignore = True
        else:
            section_items = by_priority[priority]
        lines.append(f"## {title}")
        if not section_items:
            lines.append("- none")
        for item in sorted(section_items, key=lambda value: value.message.subject.lower()):
            lines.append(
                f"- [{item.triage.priority.value}] {item.message.subject} "
                f"from {item.message.sender} — {item.triage.reason}"
            )
        lines.append("")

    lines.append("## Activity-memory candidates")
    lines.append("- none in v0")
    lines.append("")
    lines.append("## Open loops")
    open_loop_items = [
        item for item in items
        if item.message.metadata and not item.message.metadata.flags.get("replied")
        and item.triage.priority in {Priority.URGENT, Priority.NORMAL}
    ]
    if not open_loop_items:
        lines.append("- none")
    for item in sorted(open_loop_items, key=lambda value: value.message.subject.lower()):
        lines.append(f"- {item.message.subject} ({item.message.header_message_id})")
    return "\n".join(lines).rstrip() + "\n"

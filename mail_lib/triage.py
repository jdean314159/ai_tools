"""Deterministic rules-layer triage for MAIL-00 v0."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Iterable

from .thunderbird import MailMessage


class Priority(StrEnum):
    URGENT = "urgent"
    NORMAL = "normal"
    LOW = "low"
    IGNORE = "ignore"


@dataclass(frozen=True)
class TriageResult:
    header_message_id: str
    priority: Priority
    reason: str
    matched_rules: tuple[str, ...]


_NEWSLETTER_RE = re.compile(r"\b(newsletter|digest|weekly update)\b", re.IGNORECASE)
_RECEIPT_RE = re.compile(r"\b(receipt|invoice|tracking|shipped|delivery)\b", re.IGNORECASE)
_CALENDAR_RE = re.compile(r"\b(invitation|calendar|meeting|appointment)\b", re.IGNORECASE)


def _is_self_mail(message: MailMessage) -> bool:
    """Self-addressed mail: Gloda from_me flag, or sender appears among recipients.

    from_me is only set for Gloda-indexed messages; the sender-in-recipients
    check covers unindexed mail and needs no knowledge of the user's addresses.
    """
    flags = message.metadata.flags if message.metadata else {}
    if flags.get("from_me"):
        return True
    sender = (message.sender or "").strip().lower()
    if not sender:
        return False
    return sender in {(item or "").strip().lower() for item in message.recipients}


def triage_message(message: MailMessage) -> TriageResult:
    flags = message.metadata.flags if message.metadata else {}
    subject = message.subject or ""
    sender = message.sender.lower()
    rules: list[str] = []
    priority = Priority.NORMAL
    reason = "Default normal priority."

    if flags.get("mailing_list"):
        rules.append("gloda:mailing-list")
        priority = Priority.LOW
        reason = "Mailing-list message."

    if _NEWSLETTER_RE.search(subject) or "newsletter" in sender:
        rules.append("subject:newsletter")
        priority = Priority.IGNORE
        reason = "Newsletter or digest."

    if _RECEIPT_RE.search(subject):
        rules.append("subject:receipt-or-tracking")
        priority = Priority.LOW
        reason = "Automated receipt/tracking style message."

    if _CALENDAR_RE.search(subject):
        rules.append("subject:calendar")
        priority = Priority.URGENT
        reason = "Calendar or appointment related message."

    self_mail = _is_self_mail(message)
    signal_names = {folder.lower() for folder in message.signal_folders}
    if not self_mail and (flags.get("star") or any("important" in folder or "starred" in folder for folder in signal_names)):
        rules.append("signal:important-or-starred")
        priority = Priority.URGENT
        reason = "Message is starred or appears in an important signal folder."

    if not self_mail and flags.get("replied") and priority != Priority.IGNORE:
        rules.append("gloda:replied")
        priority = Priority.LOW if priority != Priority.URGENT else Priority.NORMAL
        reason = "Thread already has a reply; demoted."

    if self_mail:
        rules.append("self-mail")
        priority = Priority.LOW
        reason = "Self-addressed mail (likely platform transfer); demoted."

    return TriageResult(
        header_message_id=message.header_message_id,
        priority=priority,
        reason=reason,
        matched_rules=tuple(rules or ["default:normal"]),
    )


def triage_messages(messages: Iterable[MailMessage]) -> list[TriageResult]:
    return [triage_message(message) for message in messages]

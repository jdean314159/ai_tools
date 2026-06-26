"""Deterministic rules-layer triage for MAIL-00 v0."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
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

# A starred message older than this is not treated as urgent. Tune as needed.
URGENT_MAX_AGE_DAYS = 183  # ~6 months (starred mail)
CALENDAR_MAX_AGE_DAYS = 31  # ~1 month (calendar mail goes stale faster)


def _is_recent(date_iso: str | None, *, max_age_days: int = URGENT_MAX_AGE_DAYS) -> bool:
    """True if the message date parses and is within max_age_days of now.

    Unknown/unparseable dates return False: do not promote what cannot be dated.
    """
    if not date_iso:
        return False
    try:
        when = datetime.fromisoformat(date_iso)
    except ValueError:
        return False
    now = datetime.now(when.tzinfo) if when.tzinfo else datetime.now()
    return (now - when) <= timedelta(days=max_age_days)


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
        if _is_recent(message.date, max_age_days=CALENDAR_MAX_AGE_DAYS):
            priority = Priority.URGENT
            reason = "Recent calendar or appointment message."
        else:
            priority = Priority.NORMAL
            reason = "Calendar or appointment message, but not recent."

    self_mail = _is_self_mail(message)
    if not self_mail and flags.get("star") and _is_recent(message.date):
        rules.append("gloda:starred-recent")
        priority = Priority.URGENT
        reason = "You starred this message and it is recent."

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

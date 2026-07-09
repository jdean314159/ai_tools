"""Deterministic local mail reading, rules, indexing, and triage helpers."""

from .thunderbird import (
    MailMessage,
    MessageMetadata,
    iter_messages,
    load_message_bodies,
    load_message_body,
)
from .triage import Priority, TriageResult, triage_message, triage_messages

__all__ = [
    "MailMessage",
    "MessageMetadata",
    "Priority",
    "TriageResult",
    "iter_messages",
    "load_message_bodies",
    "load_message_body",
    "triage_message",
    "triage_messages",
]

"""Deterministic local mail reading, rules, indexing, and triage helpers."""

from .thunderbird import MailMessage, MessageMetadata, iter_messages
from .triage import Priority, TriageResult, triage_message, triage_messages

__all__ = [
    "MailMessage",
    "MessageMetadata",
    "Priority",
    "TriageResult",
    "iter_messages",
    "triage_message",
    "triage_messages",
]

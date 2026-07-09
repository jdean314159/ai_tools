"""Mark-read propagation workflow.

The local read ledger remains the source of truth for the UI. This workflow
only records whether the explicit user-authorized mark-read action also reached
the configured IMAP server.
"""
from __future__ import annotations

from dataclasses import dataclass
import imaplib
from typing import Callable

from mail_lib.thunderbird import MailMessage

from .imap_seen import mark_messages_seen
from .imap_trash import ImapAccount
from .store import AssistantStore


@dataclass(frozen=True)
class SeenOutcome:
    message_id: str
    subject: str
    status: str
    detail: str


class SeenWorkflow:
    def __init__(
        self,
        store: AssistantStore,
        accounts: tuple[ImapAccount, ...],
        *,
        prefs_cache: dict | None = None,
        connector: Callable[..., imaplib.IMAP4_SSL] = imaplib.IMAP4_SSL,
    ) -> None:
        self.store = store
        self.accounts = accounts
        self.prefs_cache = prefs_cache
        self.connector = connector

    def propagate(self, messages: tuple[MailMessage, ...]) -> tuple[SeenOutcome, ...]:
        if not messages:
            return ()
        if not self.accounts:
            outcomes = []
            for message in messages:
                detail = "No IMAP accounts are configured; local read state recorded only."
                self.store.record_seen_propagation(
                    message.header_message_id,
                    status="skipped",
                    detail=detail,
                )
                outcomes.append(
                    SeenOutcome(
                        message_id=message.header_message_id,
                        subject=message.subject,
                        status="skipped",
                        detail=detail,
                    )
                )
            return tuple(outcomes)

        for message in messages:
            self.store.record_seen_propagation(
                message.header_message_id,
                status="pending",
                detail="IMAP \\Seen propagation pending.",
            )
        results = mark_messages_seen(
            messages,
            self.accounts,
            connector=self.connector,
            prefs_cache=self.prefs_cache,
        )
        outcomes = []
        for message in messages:
            detail = results.get(message.header_message_id)
            if detail is None:
                status = "succeeded"
                detail = "Marked \\Seen on the IMAP server."
            else:
                status = "failed"
            self.store.record_seen_propagation(
                message.header_message_id,
                status=status,
                detail=detail,
            )
            outcomes.append(
                SeenOutcome(
                    message_id=message.header_message_id,
                    subject=message.subject,
                    status=status,
                    detail=detail,
                )
            )
        return tuple(outcomes)

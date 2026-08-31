"""Explicit IMAP \\Seen propagation for locally marked-read messages."""

from __future__ import annotations

from dataclasses import dataclass
import imaplib
import os
import ssl
from typing import Callable

from mail_lib.thunderbird import MailMessage

from .imap_trash import (
    ImapAccount,
    _PrefsCache,
    _locate_message_uids,
    _post_login_capabilities,
    _quoted_mailbox,
    _unexpected_match_count_error,
    _validated_message_id,
    account_for_message,
)


@dataclass(frozen=True)
class _SeenCandidate:
    message: MailMessage
    account: ImapAccount
    folder: str
    message_id: str


def validate_seen_candidate(
    message: MailMessage,
    accounts: tuple[ImapAccount, ...],
    *,
    prefs_cache: _PrefsCache | None = None,
) -> tuple[ImapAccount, str]:
    """Resolve and validate every attacker-controlled IMAP command argument."""
    account, folder = account_for_message(message, accounts, prefs_cache=prefs_cache)
    _validated_message_id(message.header_message_id)
    _quoted_mailbox(folder)
    return account, folder


def _seen_candidate(
    message: MailMessage,
    accounts: tuple[ImapAccount, ...],
    *,
    prefs_cache: _PrefsCache | None = None,
) -> _SeenCandidate:
    account, folder = validate_seen_candidate(
        message,
        accounts,
        prefs_cache=prefs_cache,
    )
    return _SeenCandidate(
        message=message,
        account=account,
        folder=folder,
        message_id=_validated_message_id(message.header_message_id),
    )


class _ImapSeenSession:
    def __init__(
        self,
        account: ImapAccount,
        *,
        connector: Callable[..., imaplib.IMAP4_SSL],
    ) -> None:
        self.account = account
        self.connector = connector
        self.connection: imaplib.IMAP4_SSL | None = None
        self.gmail_extensions = False

    def __enter__(self) -> "_ImapSeenSession":
        password = os.getenv(self.account.password_env)
        if not password:
            raise RuntimeError(
                f"Required password environment variable is unset: {self.account.password_env}"
            )
        connection = self.connector(
            self.account.host,
            self.account.port,
            ssl_context=ssl.create_default_context(),
            timeout=30,
        )
        self.connection = connection
        status, _ = connection.login(self.account.username, password)
        if status != "OK":
            raise RuntimeError("IMAP login failed")
        capabilities = _post_login_capabilities(connection)
        self.gmail_extensions = "X-GM-EXT-1" in capabilities
        return self

    def __exit__(self, *_exc_info) -> None:
        if self.connection is None:
            return
        try:
            self.connection.logout()
        except Exception:
            pass

    def _uids(self, candidate: _SeenCandidate) -> list[bytes]:
        if self.connection is None:
            raise RuntimeError("IMAP session is not open")
        _, uids = _locate_message_uids(
            self.connection,
            candidate.folder,
            candidate.message_id,
            gmail_extensions=self.gmail_extensions,
            readonly=False,
        )
        if len(uids) != 1:
            raise _unexpected_match_count_error(len(uids))
        return uids

    def mark_seen(self, candidate: _SeenCandidate) -> None:
        uids = self._uids(candidate)
        if self.connection is None:
            raise RuntimeError("IMAP session is not open")
        status, _ = self.connection.uid("STORE", uids[0], "+FLAGS.SILENT", r"(\Seen)")
        if status != "OK":
            raise RuntimeError("IMAP STORE \\Seen failed")


def mark_messages_seen(
    messages: tuple[MailMessage, ...],
    accounts: tuple[ImapAccount, ...],
    *,
    connector: Callable[..., imaplib.IMAP4_SSL] = imaplib.IMAP4_SSL,
    prefs_cache: _PrefsCache | None = None,
) -> dict[str, str | None]:
    """Propagate \\Seen with one IMAP login per account; return per-message errors."""
    outcomes: dict[str, str | None] = {message.header_message_id: None for message in messages}
    grouped: dict[ImapAccount, list[_SeenCandidate]] = {}
    for message in messages:
        try:
            candidate = _seen_candidate(message, accounts, prefs_cache=prefs_cache)
        except Exception as exc:
            outcomes[message.header_message_id] = str(exc)
            continue
        grouped.setdefault(candidate.account, []).append(candidate)

    for account, candidates in grouped.items():
        try:
            with _ImapSeenSession(account, connector=connector) as session:
                for candidate in candidates:
                    try:
                        session.mark_seen(candidate)
                    except Exception as exc:
                        outcomes[candidate.message.header_message_id] = str(exc)
                    else:
                        outcomes[candidate.message.header_message_id] = None
        except Exception as exc:
            for candidate in candidates:
                outcomes[candidate.message.header_message_id] = str(exc)
    return outcomes

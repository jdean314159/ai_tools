"""Batch IMAP Trash proposal and commit orchestration."""

from __future__ import annotations

from dataclasses import dataclass
import secrets
import time

from mail_lib.thunderbird import MailMessage

from .imap_trash import (
    ImapAccount,
    ImapMessageNotFound,
    move_messages_to_trash,
    validate_move_candidate,
    verify_messages_available_for_move,
)


@dataclass(frozen=True)
class TrashPreviewRow:
    message: MailMessage
    host: str
    username: str
    folder: str
    trash_folder: str


@dataclass(frozen=True)
class TrashOutcome:
    message_id: str
    subject: str
    status: str
    detail: str


class TrashProposalUnavailable(RuntimeError):
    def __init__(self, skipped: tuple[TrashOutcome, ...]) -> None:
        self.skipped = skipped
        detail = skipped[0].detail if skipped else "No messages are available to move"
        super().__init__(detail)


class TrashWorkflow:
    def __init__(
        self,
        accounts: tuple[ImapAccount, ...],
        *,
        prefs_cache: dict | None = None,
        token_ttl_seconds: float = 600.0,
    ) -> None:
        self.accounts = accounts
        self.prefs_cache = prefs_cache
        self.token_ttl_seconds = token_ttl_seconds
        self._pending: dict[str, tuple[tuple[str, ...], float]] = {}

    def status_for(self, message: MailMessage) -> tuple[bool, str]:
        try:
            account, folder = validate_move_candidate(
                message,
                self.accounts,
                prefs_cache=self.prefs_cache,
            )
        except ValueError as exc:
            return False, str(exc)
        return True, f"Trash target: {account.username} {folder} → {account.trash_folder}"

    def propose(
        self, messages: tuple[MailMessage, ...]
    ) -> tuple[str, tuple[TrashPreviewRow, ...], tuple[TrashOutcome, ...]]:
        rows = []
        for message in messages:
            account, folder = validate_move_candidate(
                message,
                self.accounts,
                prefs_cache=self.prefs_cache,
            )
            rows.append(
                TrashPreviewRow(
                    message=message,
                    host=account.host,
                    username=account.username,
                    folder=folder,
                    trash_folder=account.trash_folder,
                )
            )
        skipped: tuple[TrashOutcome, ...] = ()
        try:
            verify_messages_available_for_move(
                messages,
                self.accounts,
                prefs_cache=self.prefs_cache,
            )
        except ImapMessageNotFound:
            rows, skipped = self._filter_available_rows(tuple(rows))
        token = secrets.token_urlsafe(32)
        now = time.time()
        for expired_token in [key for key, value in self._pending.items() if value[1] < now]:
            self._pending.pop(expired_token, None)
        self._pending[token] = (
            tuple(row.message.header_message_id for row in rows),
            now + self.token_ttl_seconds,
        )
        return token, tuple(rows), skipped

    def _filter_available_rows(
        self, rows: tuple[TrashPreviewRow, ...]
    ) -> tuple[list[TrashPreviewRow], tuple[TrashOutcome, ...]]:
        available: list[TrashPreviewRow] = []
        skipped = []
        for row in rows:
            try:
                verify_messages_available_for_move(
                    (row.message,),
                    self.accounts,
                    prefs_cache=self.prefs_cache,
                )
            except ImapMessageNotFound as exc:
                skipped.append(
                    TrashOutcome(
                        message_id=row.message.header_message_id,
                        subject=row.message.subject,
                        status="skipped",
                        detail=(
                            f"{exc} Searched {row.message.header_message_id!r} "
                            f"on {row.username}@{row.host}, starting from source "
                            f"folder {row.folder!r}."
                        ),
                    )
                )
            else:
                available.append(row)
        if not available and skipped:
            raise TrashProposalUnavailable(tuple(skipped))
        return available, tuple(skipped)

    def pop_pending(self, token: str) -> tuple[str, ...] | None:
        pending = self._pending.pop(token, None)
        if pending is None or pending[1] < time.time():
            return None
        return pending[0]

    def commit(self, messages: tuple[MailMessage, ...]) -> tuple[TrashOutcome, ...]:
        if not messages:
            return ()
        move_results = move_messages_to_trash(
            messages,
            self.accounts,
            prefs_cache=self.prefs_cache,
        )
        outcomes = []
        for message in messages:
            detail = move_results.get(message.header_message_id)
            if detail is None:
                outcomes.append(
                    TrashOutcome(
                        message_id=message.header_message_id,
                        subject=message.subject,
                        status="moved",
                        detail="Moved to Trash.",
                    )
                )
            else:
                outcomes.append(
                    TrashOutcome(
                        message_id=message.header_message_id,
                        subject=message.subject,
                        status="failed",
                        detail=detail,
                    )
                )
        return tuple(outcomes)

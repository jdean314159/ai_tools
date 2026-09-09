"""External grader for the mail triage target at commit f9451b2.

These regressions were derived from fixes committed after the target. They are
expected to fail 3/3 when ``mail_lib`` is imported from the target and pass 3/3
when imported from corrected reference commit 8d36243 or a descendant.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from mail_lib.thunderbird import MailMessage, MessageMetadata
from mail_lib.triage import Priority, triage_message


def _message(
    *,
    message_id: str,
    subject: str,
    date: str | None,
    sender: str = "sender@example.test",
    recipients: tuple[str, ...] = ("user@example.test",),
    starred: bool = False,
    signal_folders: tuple[str, ...] = (),
) -> MailMessage:
    metadata = None
    if starred:
        metadata = MessageMetadata(
            header_message_id=message_id,
            message_key=None,
            folder_id=None,
            conversation_id=None,
            date=None,
            sender_id=None,
            flags={"star": True},
        )
    return MailMessage(
        header_message_id=message_id,
        subject=subject,
        body="Synthetic external-grader message.",
        sender=sender,
        recipients=recipients,
        date=date,
        source_folder="INBOX",
        signal_folders=signal_folders,
        metadata=metadata,
    )


def test_self_addressed_transfer_is_demoted() -> None:
    message = _message(
        message_id="self-addressed@example.test",
        subject="Calendar invitation: account transfer",
        date=datetime.now().isoformat(),
        sender="user@example.test",
        recipients=("user@example.test",),
        signal_folders=("Important",),
    )

    result = triage_message(message)

    assert result.priority == Priority.LOW
    assert "self-mail" in result.matched_rules


def test_old_starred_mail_is_not_promoted_to_urgent() -> None:
    message = _message(
        message_id="old-starred@example.test",
        subject="Project note",
        date=(datetime.now() - timedelta(days=400)).isoformat(),
        starred=True,
    )

    result = triage_message(message)

    assert result.priority == Priority.NORMAL
    assert "gloda:starred-recent" not in result.matched_rules


def test_old_calendar_mail_is_not_promoted_to_urgent() -> None:
    message = _message(
        message_id="old-calendar@example.test",
        subject="Calendar invitation: old project sync",
        date=(datetime.now() - timedelta(days=90)).isoformat(),
    )

    result = triage_message(message)

    assert result.priority == Priority.NORMAL
    assert "subject:calendar" in result.matched_rules

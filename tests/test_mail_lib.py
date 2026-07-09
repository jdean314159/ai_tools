from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import mailbox
import sqlite3
from pathlib import Path

import pytest

from mail_lib.digest import render_digest
from mail_lib.indexer import MailIndex
from mail_lib.thunderbird import (
    MailMessage,
    MessageMetadata,
    _merge_messages,
    _message_from_mbox,
    discover_mbox_files,
    iter_messages,
    load_msf_read_states,
    load_gloda_metadata,
    normalize_message_id,
    open_gloda_readonly,
)
from mail_lib.triage import Priority, triage_message, triage_messages


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "mail_lib"


def test_mozilla_status_supplies_local_read_state_without_gloda(tmp_path: Path) -> None:
    raw = EmailMessage()
    raw["Message-ID"] = "<read-locally@example.test>"
    raw["From"] = "sender@example.test"
    raw["To"] = "user@example.test"
    raw["X-Mozilla-Status"] = "0001"
    raw.set_content("body")

    message = _message_from_mbox(
        raw,
        mbox_path=tmp_path / "Inbox",
        folder_label="Inbox",
        metadata=None,
    )

    assert message is not None
    assert message.local_read is True
    assert message.metadata is None


def test_msf_read_state_overrides_stale_mbox_header(tmp_path: Path) -> None:
    msf = tmp_path / "INBOX.msf"
    msf.write_text(
        """
// <!-- <mdb:mork:z v="1.4"/> -->
< <(80=ns:msg:db:row:scope:msgs:all)(83=message-id)(88=flags)> >
<(90
    =stale-local@example.test)>
[-1(^83^90)(^88=80)]
""",
        encoding="utf-8",
    )

    states = load_msf_read_states(msf)

    assert states == {"stale-local@example.test": False}


def test_iter_messages_uses_msf_state_when_mbox_status_is_stale(tmp_path: Path) -> None:
    folder = tmp_path / "ImapMail" / "imap.example.test"
    folder.mkdir(parents=True)
    inbox = folder / "INBOX"
    message = EmailMessage()
    message["Message-ID"] = "<stale-local@example.test>"
    message["From"] = "sender@example.test"
    message["To"] = "user@example.test"
    message["Subject"] = "Unread in Thunderbird"
    message["X-Mozilla-Status"] = "0001"
    message.set_content("body")
    box = mailbox.mbox(inbox)
    try:
        box.add(message)
        box.flush()
    finally:
        box.close()
    inbox.with_name("INBOX.msf").write_text(
        """
// <!-- <mdb:mork:z v="1.4"/> -->
< <(80=ns:msg:db:row:scope:msgs:all)(83=message-id)(88=flags)> >
<(90
    =stale-local@example.test)>
[-1(^83^90)(^88=80)]
""",
        encoding="utf-8",
    )

    [loaded] = list(iter_messages(tmp_path))

    assert loaded.header_message_id == "stale-local@example.test"
    assert loaded.local_read is False
    assert loaded.read_state_source == "msf"


def test_msf_read_state_wins_when_duplicate_has_stale_mbox_state() -> None:
    msf_read = MailMessage(
        header_message_id="duplicate@example.test",
        subject="Duplicate",
        body="body",
        sender="sender@example.test",
        recipients=("user@example.test",),
        date=None,
        source_folder="INBOX",
        local_read=True,
        read_state_source="msf",
    )
    stale_mbox_unread = MailMessage(
        header_message_id="duplicate@example.test",
        subject="Duplicate",
        body="body",
        sender="sender@example.test",
        recipients=("user@example.test",),
        date=None,
        source_folder=None,
        signal_folders=("Important",),
        local_read=False,
        read_state_source="mbox",
    )

    merged = _merge_messages(msf_read, stale_mbox_unread)
    reverse = _merge_messages(stale_mbox_unread, msf_read)

    assert merged.local_read is True
    assert merged.read_state_source == "msf"
    assert reverse.local_read is True
    assert reverse.read_state_source == "msf"


def test_iter_messages_respects_newer_than_window(tmp_path: Path) -> None:
    folder = tmp_path / "ImapMail" / "imap.example.test"
    folder.mkdir(parents=True)
    inbox = folder / "INBOX"
    box = mailbox.mbox(inbox)
    try:
        for message_id, date in (
            ("old@example.test", "Mon, 01 Jun 2026 12:00:00 +0000"),
            ("new@example.test", "Wed, 08 Jul 2026 12:00:00 +0000"),
        ):
            message = EmailMessage()
            message["Message-ID"] = f"<{message_id}>"
            message["From"] = "sender@example.test"
            message["To"] = "user@example.test"
            message["Subject"] = message_id
            message["Date"] = date
            message.set_content("body")
            box.add(message)
        box.flush()
    finally:
        box.close()
    inbox.with_name("INBOX.msf").write_text("synthetic msf marker", encoding="utf-8")

    messages = list(
        iter_messages(
            tmp_path,
            newer_than=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
    )

    assert [message.header_message_id for message in messages] == ["new@example.test"]


def test_fixtures_use_only_reserved_example_data() -> None:
    fixture_text = ""
    for path in FIXTURE_ROOT.rglob("*"):
        if path.is_file() and path.suffix != ".sqlite":
            fixture_text += path.read_text(encoding="utf-8", errors="ignore")
    assert "@example.test" in fixture_text
    assert "gmail.com" not in fixture_text.lower()
    assert "outlook.office365.com" not in fixture_text.lower()


def test_gloda_readonly_and_message_id_metadata_join() -> None:
    conn = open_gloda_readonly(FIXTURE_ROOT / "gloda_fixture.sqlite")
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE should_fail (id INTEGER)")
    finally:
        conn.close()

    metadata = load_gloda_metadata(FIXTURE_ROOT)
    assert "important-1@example.test" in metadata
    important = metadata["important-1@example.test"]
    assert important.sender is not None
    assert important.sender.address == "ceo@example.test"
    assert important.recipients[0].address == "user@example.test"
    assert important.flags["star"] is True
    assert important.flags["read"] is True


def test_reader_discovers_extensionless_mboxes_and_deduplicates_signal_folders() -> None:
    mboxes = discover_mbox_files(FIXTURE_ROOT)
    labels = {path.name for path in mboxes}
    assert "All Mail" in labels
    assert "Important" in labels
    assert all(path.suffix != ".mbox" for path in mboxes)

    messages = list(iter_messages(FIXTURE_ROOT))
    by_id = {message.header_message_id: message for message in messages}
    assert len(messages) == len(by_id)

    important = by_id["important-1@example.test"]
    assert important.has_gloda_metadata
    assert important.source_folder == "[Gmail]/All Mail"
    assert "Important" in important.signal_folders
    assert important.subject == "Calendar invitation: project review"
    assert "Please review the project plan" in important.body

    mbox_only = by_id["unindexed-1@example.test"]
    assert not mbox_only.has_gloda_metadata
    assert mbox_only.subject == "Unindexed local note"


def test_message_id_normalization() -> None:
    assert normalize_message_id("<important-1@example.test>") == "important-1@example.test"
    assert normalize_message_id(" important-1@example.test ") == "important-1@example.test"


def test_rules_layer_triage_hits_expected_fixture_branches() -> None:
    messages = list(iter_messages(FIXTURE_ROOT))
    results = {result.header_message_id: result for result in triage_messages(messages)}

    assert results["important-1@example.test"].priority == Priority.NORMAL
    assert "subject:calendar" in results["important-1@example.test"].matched_rules
    assert results["newsletter-1@example.test"].priority == Priority.IGNORE
    assert results["list-1@example.test"].priority in {Priority.LOW, Priority.IGNORE}
    assert results["replied-1@example.test"].priority == Priority.LOW


def test_rules_layer_demotes_unindexed_self_addressed_mail() -> None:
    message = MailMessage(
        header_message_id="self-mail@example.test",
        subject="Calendar invitation: self transfer",
        body="Fake self-addressed platform-transfer message.",
        sender="user@example.test",
        recipients=("user@example.test",),
        date=None,
        source_folder="INBOX",
        signal_folders=("Important",),
        metadata=None,
    )

    result = triage_message(message)

    assert result.priority == Priority.LOW
    assert "self-mail" in result.matched_rules


def test_rules_layer_promotes_only_recent_starred_mail() -> None:
    recent = datetime.now().isoformat()
    old = (datetime.now() - timedelta(days=400)).isoformat()

    def starred_message(date: str) -> MailMessage:
        return MailMessage(
            header_message_id=f"starred-{date}@example.test",
            subject="Project note",
            body="Fake starred project note.",
            sender="sender@example.test",
            recipients=("user@example.test",),
            date=date,
            source_folder="[Gmail]/All Mail",
            metadata=MessageMetadata(
                header_message_id=f"starred-{date}@example.test",
                message_key=None,
                folder_id=None,
                conversation_id=None,
                date=None,
                sender_id=None,
                flags={"star": True},
            ),
        )

    recent_result = triage_message(starred_message(recent))
    old_result = triage_message(starred_message(old))

    assert recent_result.priority == Priority.URGENT
    assert "gloda:starred-recent" in recent_result.matched_rules
    assert old_result.priority == Priority.NORMAL
    assert "gloda:starred-recent" not in old_result.matched_rules


def test_rules_layer_promotes_only_recent_calendar_mail() -> None:
    recent = datetime.now().isoformat()
    old = (datetime.now() - timedelta(days=90)).isoformat()

    def calendar_message(date: str) -> MailMessage:
        return MailMessage(
            header_message_id=f"calendar-{date}@example.test",
            subject="Calendar invitation: project sync",
            body="Fake calendar message.",
            sender="sender@example.test",
            recipients=("user@example.test",),
            date=date,
            source_folder="[Gmail]/All Mail",
        )

    recent_result = triage_message(calendar_message(recent))
    old_result = triage_message(calendar_message(old))

    assert recent_result.priority == Priority.URGENT
    assert "subject:calendar" in recent_result.matched_rules
    assert old_result.priority == Priority.NORMAL
    assert "subject:calendar" in old_result.matched_rules


def test_indexer_records_and_skips_processed_messages(tmp_path: Path) -> None:
    messages = list(iter_messages(FIXTURE_ROOT))
    results = triage_messages(messages)
    with MailIndex(tmp_path / "index.db") as index:
        assert len(index.new_messages(messages)) == len(messages)
        index.record_results(messages, results, processed_at=123.0)
        assert index.new_messages(messages) == []
        assert index.get_priority("important-1@example.test") == "normal"


def test_digest_contains_expected_sections_and_fake_messages() -> None:
    messages = list(iter_messages(FIXTURE_ROOT))
    digest = render_digest(messages, triage_messages(messages))
    assert "## Urgent" in digest
    assert "## Normal" in digest
    assert "## Suggested ignores" in digest
    assert "## Activity-memory candidates" in digest
    assert "## Open loops" in digest
    assert "Calendar invitation: project review" in digest
    assert "Weekly Newsletter" in digest

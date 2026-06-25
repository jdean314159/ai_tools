from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from mail_lib.digest import render_digest
from mail_lib.indexer import MailIndex
from mail_lib.thunderbird import (
    discover_mbox_files,
    iter_messages,
    load_gloda_metadata,
    normalize_message_id,
    open_gloda_readonly,
)
from mail_lib.triage import Priority, triage_messages


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "mail_lib"


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

    assert results["important-1@example.test"].priority == Priority.URGENT
    assert "signal:important-or-starred" in results["important-1@example.test"].matched_rules
    assert results["newsletter-1@example.test"].priority == Priority.IGNORE
    assert results["list-1@example.test"].priority in {Priority.LOW, Priority.IGNORE}
    assert results["replied-1@example.test"].priority == Priority.LOW


def test_indexer_records_and_skips_processed_messages(tmp_path: Path) -> None:
    messages = list(iter_messages(FIXTURE_ROOT))
    results = triage_messages(messages)
    with MailIndex(tmp_path / "index.db") as index:
        assert len(index.new_messages(messages)) == len(messages)
        index.record_results(messages, results, processed_at=123.0)
        assert index.new_messages(messages) == []
        assert index.get_priority("important-1@example.test") == "urgent"


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

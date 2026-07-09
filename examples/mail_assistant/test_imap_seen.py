from __future__ import annotations

from dataclasses import replace

from mail_lib.thunderbird import MailMessage, MessageMetadata

from .imap_seen import mark_messages_seen, validate_seen_candidate
from .imap_trash import ImapAccount
from .seen_workflow import SeenWorkflow
from .store import AssistantStore


def _message(message_id: str = "one@example.test") -> MailMessage:
    metadata = MessageMetadata(
        header_message_id=message_id,
        message_key=None,
        folder_id=None,
        conversation_id=None,
        date=None,
        sender_id=None,
        folder_uri="imap://user%40example.test@imap.example.test/INBOX",
    )
    return MailMessage(
        header_message_id=message_id,
        subject="Fixture",
        body="Body",
        sender="sender@example.test",
        recipients=("user@example.test",),
        date=None,
        source_folder="INBOX",
        metadata=metadata,
    )


class FakeImap:
    def __init__(self, *args, **kwargs) -> None:
        self.calls = [("connect", args, kwargs)]

    def login(self, username, password):
        self.calls.append(("login", username, password))
        return "OK", []

    def capability(self):
        self.calls.append(("capability",))
        return "OK", [b"IMAP4rev1 UIDPLUS"]

    def select(self, folder, readonly=False):
        self.calls.append(("select", folder, readonly))
        return "OK", []

    def uid(self, command, *args):
        self.calls.append(("uid", command, args))
        if command == "SEARCH":
            return "OK", [b"42"]
        return "OK", []

    def logout(self):
        self.calls.append(("logout",))
        return "BYE", []


def _account() -> ImapAccount:
    return ImapAccount(
        host="imap.example.test",
        username="user@example.test",
        password_env="MAIL_TEST_PASSWORD",
        trash_folder="Trash",
    )


def test_mark_seen_matches_exact_message_and_stores_seen(monkeypatch) -> None:
    monkeypatch.setenv("MAIL_TEST_PASSWORD", "secret")
    connections = []

    def connect(*args, **kwargs):
        connection = FakeImap(*args, **kwargs)
        connections.append(connection)
        return connection

    outcomes = mark_messages_seen((_message(),), (_account(),), connector=connect)

    assert outcomes == {"one@example.test": None}
    calls = connections[0].calls
    assert ("select", '"INBOX"', False) in calls
    assert (
        "uid",
        "SEARCH",
        (None, "HEADER", "Message-ID", '"<one@example.test>"'),
    ) in calls
    assert ("uid", "STORE", (b"42", "+FLAGS.SILENT", r"(\Seen)")) in calls
    assert calls[-1] == ("logout",)


def test_mark_seen_reuses_one_login_per_account(monkeypatch) -> None:
    monkeypatch.setenv("MAIL_TEST_PASSWORD", "secret")
    connections = []

    def connect(*args, **kwargs):
        connection = FakeImap(*args, **kwargs)
        connections.append(connection)
        return connection

    outcomes = mark_messages_seen(
        (
            _message(),
            replace(_message(), header_message_id="two@example.test"),
        ),
        (_account(),),
        connector=connect,
    )

    assert outcomes == {"one@example.test": None, "two@example.test": None}
    assert len(connections) == 1
    calls = connections[0].calls
    assert [call for call in calls if call[0] == "login"] == [
        ("login", "user@example.test", "secret")
    ]
    assert calls.count(("uid", "STORE", (b"42", "+FLAGS.SILENT", r"(\Seen)"))) == 2


def test_mark_seen_uses_gmail_raw_search(monkeypatch) -> None:
    monkeypatch.setenv("MAIL_TEST_PASSWORD", "secret")
    connections = []

    class GmailImap(FakeImap):
        def capability(self):
            self.calls.append(("capability",))
            return "OK", [b"IMAP4rev1 UIDPLUS X-GM-EXT-1"]

    def connect(*args, **kwargs):
        connection = GmailImap(*args, **kwargs)
        connections.append(connection)
        return connection

    mark_messages_seen((_message(),), (_account(),), connector=connect)

    assert (
        "uid",
        "SEARCH",
        ("X-GM-RAW", '"rfc822msgid:one@example.test"'),
    ) in connections[0].calls
    assert ("uid", "STORE", (b"42", "+FLAGS.SILENT", r"(\Seen)")) in connections[0].calls


def test_seen_candidate_rejects_unconfigured_account() -> None:
    other = replace(_account(), host="other.example.test")

    try:
        validate_seen_candidate(_message(), (other,))
    except ValueError as exc:
        assert "No unique configured IMAP account" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("candidate should have been rejected")


def test_seen_workflow_records_success_and_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MAIL_TEST_PASSWORD", "secret")
    store = AssistantStore(tmp_path / "seen.db")

    class MissingImap(FakeImap):
        def uid(self, command, *args):
            self.calls.append(("uid", command, args))
            if command == "SEARCH":
                return "OK", [b""]
            return "OK", []

    workflow = SeenWorkflow(store, (_account(),), connector=MissingImap)

    outcomes = workflow.propagate((_message(),))

    assert len(outcomes) == 1
    assert outcomes[0].status == "failed"
    assert store.seen_propagation_status("one@example.test")[0] == "failed"

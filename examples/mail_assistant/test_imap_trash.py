from __future__ import annotations

from dataclasses import replace

import pytest

from mail_lib.thunderbird import MailMessage, MessageMetadata

from .imap_trash import ImapAccount, account_for_message, move_message_to_trash


def _message() -> MailMessage:
    metadata = MessageMetadata(
        header_message_id="one@example.test",
        message_key=None,
        folder_id=None,
        conversation_id=None,
        date=None,
        sender_id=None,
        folder_uri="imap://user%40example.test@imap.example.test/INBOX",
    )
    return MailMessage(
        header_message_id="one@example.test",
        subject="Fixture",
        body="Body",
        sender="sender@example.test",
        recipients=("user@example.test",),
        date=None,
        source_folder="INBOX",
        metadata=metadata,
    )


class FakeImap:
    capabilities = (b"IMAP4rev1", b"MOVE")

    def __init__(self, *args, **kwargs) -> None:
        self.calls = [("connect", args, kwargs)]

    def login(self, username, password):
        self.calls.append(("login", username, password))
        return "OK", []

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


def test_move_to_trash_matches_account_and_uses_atomic_move(monkeypatch) -> None:
    account = ImapAccount(
        host="imap.example.test",
        username="user@example.test",
        password_env="MAIL_TEST_PASSWORD",
        trash_folder="Trash",
    )
    monkeypatch.setenv("MAIL_TEST_PASSWORD", "secret")
    connections = []

    def connect(*args, **kwargs):
        connection = FakeImap(*args, **kwargs)
        connections.append(connection)
        return connection

    move_message_to_trash(_message(), (account,), connector=connect)

    calls = connections[0].calls
    assert ("select", '"INBOX"', False) in calls
    assert ("uid", "SEARCH", (None, "HEADER", "Message-ID", "<one@example.test>")) in calls
    assert ("uid", "MOVE", (b"42", '"Trash"')) in calls
    assert calls[-1] == ("logout",)


def test_move_to_trash_fails_closed_without_mapping_or_password(monkeypatch) -> None:
    account = ImapAccount(
        host="other.example.test",
        username="user@example.test",
        password_env="MISSING_PASSWORD",
        trash_folder="Trash",
    )
    with pytest.raises(ValueError, match="No unique configured"):
        account_for_message(_message(), (account,))

    matching = replace(account, host="imap.example.test")
    monkeypatch.delenv("MISSING_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="environment variable is unset"):
        move_message_to_trash(_message(), (matching,), connector=FakeImap)


@pytest.mark.parametrize(
    "hostile_message_id",
    [
        "safe@example.test\r\nEXPUNGE",
        'safe@example.test" OR ALL',
        "safe(comment)@example.test",
        "safe[box]@example.test",
    ],
)
def test_hostile_message_id_is_rejected_before_socket_use(
    monkeypatch, hostile_message_id: str
) -> None:
    account = ImapAccount(
        host="imap.example.test",
        username="user@example.test",
        password_env="MAIL_TEST_PASSWORD",
        trash_folder="Trash",
    )
    monkeypatch.setenv("MAIL_TEST_PASSWORD", "secret")
    connection_attempted = False

    def connect(*_args, **_kwargs):
        nonlocal connection_attempted
        connection_attempted = True
        raise AssertionError("connector must not be called")

    with pytest.raises(ValueError, match="unsafe for IMAP"):
        move_message_to_trash(
            replace(_message(), header_message_id=hostile_message_id),
            (account,),
            connector=connect,
        )
    assert connection_attempted is False


@pytest.mark.parametrize("trash_folder", ["Trash\rEXPUNGE", "Trash\nEXPUNGE"])
def test_hostile_mailbox_is_rejected_before_socket_use(
    monkeypatch, trash_folder: str
) -> None:
    account = ImapAccount(
        host="imap.example.test",
        username="user@example.test",
        password_env="MAIL_TEST_PASSWORD",
        trash_folder=trash_folder,
    )
    monkeypatch.setenv("MAIL_TEST_PASSWORD", "secret")

    with pytest.raises(ValueError, match="must not contain CR or LF"):
        move_message_to_trash(
            _message(),
            (account,),
            connector=lambda *_args, **_kwargs: pytest.fail("connector called"),
        )

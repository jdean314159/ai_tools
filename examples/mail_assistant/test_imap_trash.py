from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from mail_lib.thunderbird import MailMessage, MessageMetadata

from .imap_trash import (
    ImapAccount,
    account_for_message,
    move_messages_to_trash,
    move_message_to_trash,
    validate_move_candidate,
    verify_messages_available_for_move,
    verify_message_available_for_move,
)


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
    # Model Gmail's greeting: MOVE is absent before authentication and appears
    # only in an explicit post-login CAPABILITY response.
    capabilities = (b"IMAP4rev1", b"AUTH=PLAIN")

    def __init__(self, *args, **kwargs) -> None:
        self.calls = [("connect", args, kwargs)]

    def login(self, username, password):
        self.calls.append(("login", username, password))
        return "OK", []

    def capability(self):
        self.calls.append(("capability",))
        return "OK", [b"IMAP4rev1 UIDPLUS MOVE"]

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
    assert (
        "uid",
        "SEARCH",
        ("HEADER", "Message-ID", '"<one@example.test>"'),
    ) in calls
    assert ("uid", "MOVE", (b"42", '"Trash"')) in calls
    assert calls[-1] == ("logout",)


def test_move_to_trash_uses_post_login_string_capabilities(monkeypatch) -> None:
    account = ImapAccount(
        host="imap.example.test",
        username="user@example.test",
        password_env="MAIL_TEST_PASSWORD",
        trash_folder="Trash",
    )
    monkeypatch.setenv("MAIL_TEST_PASSWORD", "secret")

    class StringCapabilityImap(FakeImap):
        capabilities = ("IMAP4REV1", "AUTH=PLAIN")

        def capability(self):
            self.calls.append(("capability",))
            return "OK", ["IMAP4REV1 UIDPLUS MOVE"]

    move_message_to_trash(_message(), (account,), connector=StringCapabilityImap)


def test_verify_message_available_for_move_is_read_only(monkeypatch) -> None:
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

    verify_message_available_for_move(_message(), (account,), connector=connect)

    calls = connections[0].calls
    assert ("select", '"INBOX"', True) in calls
    assert ("uid", "MOVE", (b"42", '"Trash"')) not in calls


def test_batch_preflight_reuses_one_login_per_account(monkeypatch) -> None:
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

    verify_messages_available_for_move(
        (
            _message(),
            replace(_message(), header_message_id="two@example.test"),
        ),
        (account,),
        connector=connect,
    )

    assert len(connections) == 1
    calls = connections[0].calls
    assert [call for call in calls if call[0] == "login"] == [
        ("login", "user@example.test", "secret")
    ]
    assert calls.count(("select", '"INBOX"', True)) == 2
    assert calls[-1] == ("logout",)


def test_batch_move_reuses_one_login_per_account(monkeypatch) -> None:
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

    outcomes = move_messages_to_trash(
        (
            _message(),
            replace(_message(), header_message_id="two@example.test"),
        ),
        (account,),
        connector=connect,
    )

    assert outcomes == {"one@example.test": None, "two@example.test": None}
    assert len(connections) == 1
    calls = connections[0].calls
    assert [call for call in calls if call[0] == "login"] == [
        ("login", "user@example.test", "secret")
    ]
    assert calls.count(("uid", "MOVE", (b"42", '"Trash"'))) == 2


def test_zero_uid_match_reports_stale_local_snapshot(monkeypatch) -> None:
    account = ImapAccount(
        host="imap.example.test",
        username="user@example.test",
        password_env="MAIL_TEST_PASSWORD",
        trash_folder="Trash",
    )
    monkeypatch.setenv("MAIL_TEST_PASSWORD", "secret")

    class MissingMessageImap(FakeImap):
        def uid(self, command, *args):
            self.calls.append(("uid", command, args))
            if command == "SEARCH":
                return "OK", [b""]
            return "OK", []

    with pytest.raises(RuntimeError, match="local Thunderbird snapshot is likely stale"):
        move_message_to_trash(_message(), (account,), connector=MissingMessageImap)


def test_gmail_uses_raw_message_id_search(monkeypatch) -> None:
    account = ImapAccount(
        host="imap.example.test",
        username="user@example.test",
        password_env="MAIL_TEST_PASSWORD",
        trash_folder="Trash",
    )
    monkeypatch.setenv("MAIL_TEST_PASSWORD", "secret")
    connections = []

    class GmailImap(FakeImap):
        def capability(self):
            self.calls.append(("capability",))
            return "OK", [b"IMAP4rev1 UIDPLUS MOVE X-GM-EXT-1"]

    def connect(*args, **kwargs):
        connection = GmailImap(*args, **kwargs)
        connections.append(connection)
        return connection

    move_message_to_trash(_message(), (account,), connector=connect)

    assert (
        "uid",
        "SEARCH",
        ("X-GM-RAW", '"rfc822msgid:one@example.test"'),
    ) in connections[0].calls
    assert not any(
        call[:2] == ("uid", "SEARCH") and "HEADER" in call[2] for call in connections[0].calls
    )


def test_gmail_retries_in_special_use_all_mailbox(monkeypatch) -> None:
    account = ImapAccount(
        host="imap.example.test",
        username="user@example.test",
        password_env="MAIL_TEST_PASSWORD",
        trash_folder="[Google Mail]/Papierkorb",
    )
    monkeypatch.setenv("MAIL_TEST_PASSWORD", "secret")
    connections = []

    class GmailDriftImap(FakeImap):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.selected = None

        def capability(self):
            self.calls.append(("capability",))
            return "OK", [b"IMAP4rev1 UIDPLUS MOVE X-GM-EXT-1"]

        def select(self, folder, readonly=False):
            self.selected = folder
            return super().select(folder, readonly)

        def list(self, reference='""', pattern="*"):
            self.calls.append(("list", reference, pattern))
            return "OK", [
                b'(\\HasNoChildren \\Trash) "/" "[Google Mail]/Papierkorb"',
                b'(\\HasNoChildren \\All) "/" "[Google Mail]/Alle Nachrichten"',
            ]

        def uid(self, command, *args):
            self.calls.append(("uid", command, args))
            if command == "SEARCH":
                if self.selected == '"[Google Mail]/Alle Nachrichten"':
                    return "OK", [b"84"]
                return "OK", [b""]
            return "OK", []

    def connect(*args, **kwargs):
        connection = GmailDriftImap(*args, **kwargs)
        connections.append(connection)
        return connection

    move_message_to_trash(_message(), (account,), connector=connect)

    calls = connections[0].calls
    assert ("list", '""', "*") in calls
    assert (
        "select",
        '"[Google Mail]/Alle Nachrichten"',
        False,
    ) in calls
    assert ("uid", "MOVE", (b"84", '"[Google Mail]/Papierkorb"')) in calls


def test_gmail_retries_raw_search_with_rfc_angle_brackets(monkeypatch) -> None:
    account = ImapAccount(
        host="imap.example.test",
        username="user@example.test",
        password_env="MAIL_TEST_PASSWORD",
        trash_folder="Trash",
    )
    monkeypatch.setenv("MAIL_TEST_PASSWORD", "secret")
    connections = []

    class GmailBracketImap(FakeImap):
        def capability(self):
            self.calls.append(("capability",))
            return "OK", [b"IMAP4rev1 UIDPLUS MOVE X-GM-EXT-1"]

        def uid(self, command, *args):
            self.calls.append(("uid", command, args))
            if command == "SEARCH":
                if args[-1] == '"rfc822msgid:<one@example.test>"':
                    return "OK", [b"91"]
                return "OK", [b""]
            return "OK", []

    def connect(*args, **kwargs):
        connection = GmailBracketImap(*args, **kwargs)
        connections.append(connection)
        return connection

    move_message_to_trash(_message(), (account,), connector=connect)

    searches = [call for call in connections[0].calls if call[:2] == ("uid", "SEARCH")]
    assert searches == [
        (
            "uid",
            "SEARCH",
            ("X-GM-RAW", '"rfc822msgid:one@example.test"'),
        ),
        (
            "uid",
            "SEARCH",
            ("X-GM-RAW", '"rfc822msgid:<one@example.test>"'),
        ),
    ]
    assert ("uid", "MOVE", (b"91", '"Trash"')) in connections[0].calls


def test_gmail_falls_back_to_header_search_for_raw_message_id_miss(monkeypatch) -> None:
    account = ImapAccount(
        host="imap.example.test",
        username="user@example.test",
        password_env="MAIL_TEST_PASSWORD",
        trash_folder="Trash",
    )
    monkeypatch.setenv("MAIL_TEST_PASSWORD", "secret")
    message_id = "jdean314159/ai_tools/check-suites/CS_kwDOSKnSks8AAAASRkhmkg/1783598783@github.com"
    connections = []

    class GmailHeaderFallbackImap(FakeImap):
        def capability(self):
            self.calls.append(("capability",))
            return "OK", [b"IMAP4rev1 UIDPLUS MOVE X-GM-EXT-1"]

        def uid(self, command, *args):
            self.calls.append(("uid", command, args))
            if command == "SEARCH" and args[-1] == f'"{message_id}"':
                return "OK", [b"77"]
            if command == "SEARCH":
                return "OK", [b""]
            return "OK", []

    def connect(*args, **kwargs):
        connection = GmailHeaderFallbackImap(*args, **kwargs)
        connections.append(connection)
        return connection

    move_message_to_trash(
        replace(_message(), header_message_id=message_id),
        (account,),
        connector=connect,
    )

    searches = [call for call in connections[0].calls if call[:2] == ("uid", "SEARCH")]
    assert searches == [
        (
            "uid",
            "SEARCH",
            ("X-GM-RAW", f'"rfc822msgid:{message_id}"'),
        ),
        (
            "uid",
            "SEARCH",
            ("X-GM-RAW", f'"rfc822msgid:<{message_id}>"'),
        ),
        (
            "uid",
            "SEARCH",
            ("HEADER", "Message-ID", f'"<{message_id}>"'),
        ),
        (
            "uid",
            "SEARCH",
            ("HEADER", "Message-ID", f'"{message_id}"'),
        ),
    ]
    assert ("uid", "MOVE", (b"77", '"Trash"')) in connections[0].calls


def test_message_id_search_quotes_valid_imap_special_characters(monkeypatch) -> None:
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

    move_message_to_trash(
        replace(_message(), header_message_id="safe%tag@example.test"),
        (account,),
        connector=connect,
    )

    assert (
        "uid",
        "SEARCH",
        ("HEADER", "Message-ID", '"<safe%tag@example.test>"'),
    ) in connections[0].calls


def test_header_search_retries_with_bare_message_id(monkeypatch) -> None:
    account = ImapAccount(
        host="imap.example.test",
        username="user@example.test",
        password_env="MAIL_TEST_PASSWORD",
        trash_folder="Trash",
    )
    monkeypatch.setenv("MAIL_TEST_PASSWORD", "secret")
    connections = []

    class BareHeaderImap(FakeImap):
        def uid(self, command, *args):
            self.calls.append(("uid", command, args))
            if command == "SEARCH" and args[-1] == '"one@example.test"':
                return "OK", [b"52"]
            if command == "SEARCH":
                return "OK", [b""]
            return "OK", []

    def connect(*args, **kwargs):
        connection = BareHeaderImap(*args, **kwargs)
        connections.append(connection)
        return connection

    move_message_to_trash(_message(), (account,), connector=connect)

    searches = [call for call in connections[0].calls if call[:2] == ("uid", "SEARCH")]
    assert searches == [
        (
            "uid",
            "SEARCH",
            ("HEADER", "Message-ID", '"<one@example.test>"'),
        ),
        (
            "uid",
            "SEARCH",
            ("HEADER", "Message-ID", '"one@example.test"'),
        ),
    ]
    assert ("uid", "MOVE", (b"52", '"Trash"')) in connections[0].calls


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


def test_move_candidate_rejects_message_already_in_trash() -> None:
    account = ImapAccount(
        host="imap.example.test",
        username="user@example.test",
        password_env="MAIL_TEST_PASSWORD",
        trash_folder="Trash",
    )
    message = replace(
        _message(),
        metadata=replace(
            _message().metadata,
            folder_uri="imap://user%40example.test@imap.example.test/Trash",
        ),
    )

    with pytest.raises(ValueError, match="already in the configured Trash"):
        validate_move_candidate(message, (account,))


def test_account_resolution_falls_back_to_unique_imap_mbox_directory() -> None:
    account = ImapAccount(
        host="imap.example.test",
        username="user@example.test",
        password_env="MAIL_TEST_PASSWORD",
        trash_folder="Trash",
    )
    message = replace(
        _message(),
        metadata=None,
        mbox_path=Path("/profile/ImapMail/imap.example.test/INBOX"),
    )

    resolved, folder = account_for_message(message, (account,))

    assert resolved == account
    assert folder == "INBOX"


def test_mbox_fallback_rejects_ambiguous_accounts() -> None:
    account = ImapAccount(
        host="imap.example.test",
        username="first@example.test",
        password_env="FIRST_PASSWORD",
        trash_folder="Trash",
    )
    message = replace(
        _message(),
        metadata=None,
        mbox_path=Path("/profile/ImapMail/imap.example.test/INBOX"),
    )

    with pytest.raises(ValueError, match="No unique configured"):
        account_for_message(
            message,
            (account, replace(account, username="second@example.test")),
        )


def test_mbox_fallback_uses_thunderbird_prefs_for_shared_host(tmp_path: Path) -> None:
    first = ImapAccount(
        host="imap.gmail.com",
        username="first@example.test",
        password_env="FIRST_PASSWORD",
        trash_folder="[Gmail]/Trash",
    )
    second = replace(first, username="second@example.test")
    (tmp_path / "ImapMail" / "imap.gmail-2.com").mkdir(parents=True)
    (tmp_path / "prefs.js").write_text(
        'user_pref("mail.server.server4.directory-rel", '
        '"[ProfD]ImapMail/imap.gmail-2.com");\n'
        'user_pref("mail.server.server4.hostname", "imap.gmail.com");\n'
        'user_pref("mail.server.server4.userName", "second@example.test");\n',
        encoding="utf-8",
    )
    message = replace(
        _message(),
        metadata=None,
        mbox_path=tmp_path / "ImapMail" / "imap.gmail-2.com" / "INBOX",
    )

    resolved, folder = account_for_message(message, (first, second))

    assert resolved == second
    assert folder == "INBOX"


def test_mbox_fallback_uses_absolute_thunderbird_prefs_directory(
    tmp_path: Path,
) -> None:
    first = ImapAccount(
        host="imap.gmail.com",
        username="first@example.test",
        password_env="FIRST_PASSWORD",
        trash_folder="[Gmail]/Trash",
    )
    second = replace(first, username="second@example.test")
    account_directory = tmp_path / "ImapMail" / "imap.gmail-2.com"
    account_directory.mkdir(parents=True)
    (tmp_path / "prefs.js").write_text(
        'user_pref("mail.server.server4.directory", '
        f'"{account_directory.as_posix()}");\n'
        + 'user_pref("mail.server.server4.hostname", "imap.gmail.com");\n'
        + 'user_pref("mail.server.server4.userName", "second@example.test");\n',
        encoding="utf-8",
    )
    message = replace(
        _message(),
        metadata=None,
        mbox_path=account_directory / "INBOX",
    )

    resolved, folder = account_for_message(message, (first, second))

    assert resolved == second
    assert folder == "INBOX"


def test_mbox_fallback_can_reuse_cached_thunderbird_prefs(tmp_path: Path) -> None:
    first = ImapAccount(
        host="imap.gmail.com",
        username="first@example.test",
        password_env="FIRST_PASSWORD",
        trash_folder="[Gmail]/Trash",
    )
    second = replace(first, username="second@example.test")
    account_directory = tmp_path / "ImapMail" / "imap.gmail-2.com"
    account_directory.mkdir(parents=True)
    prefs_path = tmp_path / "prefs.js"
    prefs_path.write_text(
        'user_pref("mail.server.server4.directory-rel", '
        '"[ProfD]ImapMail/imap.gmail-2.com");\n'
        'user_pref("mail.server.server4.hostname", "imap.gmail.com");\n'
        'user_pref("mail.server.server4.userName", "second@example.test");\n',
        encoding="utf-8",
    )
    message = replace(
        _message(),
        metadata=None,
        mbox_path=account_directory / "INBOX",
    )
    prefs_cache = {}

    resolved, _folder = account_for_message(
        message,
        (first, second),
        prefs_cache=prefs_cache,
    )
    prefs_path.write_text(
        'user_pref("mail.server.server4.directory-rel", '
        '"[ProfD]ImapMail/imap.gmail-2.com");\n'
        'user_pref("mail.server.server4.hostname", "imap.gmail.com");\n'
        'user_pref("mail.server.server4.userName", "first@example.test");\n',
        encoding="utf-8",
    )
    cached_resolved, _folder = account_for_message(
        message,
        (first, second),
        prefs_cache=prefs_cache,
    )

    assert resolved == second
    assert cached_resolved == second


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
def test_hostile_mailbox_is_rejected_before_socket_use(monkeypatch, trash_folder: str) -> None:
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

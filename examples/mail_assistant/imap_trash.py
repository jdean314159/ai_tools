"""Explicit, confirmed IMAP move-to-trash support."""
from __future__ import annotations

from dataclasses import dataclass
import imaplib
import json
import os
from pathlib import Path
import re
import ssl
import tomllib
from typing import Callable

from mail_lib.thunderbird import MailMessage, parse_folder_uri


_MESSAGE_ID_RE = re.compile(
    r"^[A-Za-z0-9!#$%&'*+\-/=?^_`{|}~.]+@[A-Za-z0-9.-]+$"
)
_SERVER_PREF_RE = re.compile(
    r'^user_pref\("mail\.server\.(server\d+)\.(directory|directory-rel|hostname|realhostname|userName)",\s*(.+)\);$'
)
_LIST_RESPONSE_RE = re.compile(
    r'^\((?P<flags>[^)]*)\)\s+(?:NIL|"(?:\\.|[^"\\])*")\s+(?P<mailbox>.+)$'
)


@dataclass(frozen=True)
class ImapAccount:
    host: str
    username: str
    password_env: str
    trash_folder: str
    port: int = 993


def _quoted_mailbox(value: str) -> str:
    if "\r" in value or "\n" in value:
        raise ValueError("IMAP mailbox names must not contain CR or LF")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _validated_message_id(value: str) -> str:
    normalized = value.strip()
    if not _MESSAGE_ID_RE.fullmatch(normalized) or normalized.count("@") != 1:
        raise ValueError("Message-ID contains characters unsafe for IMAP search")
    return normalized


def load_imap_accounts(path: Path) -> tuple[ImapAccount, ...]:
    if not path.exists():
        return ()
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    raw_accounts = data.get("account", [])
    if not isinstance(raw_accounts, list):
        raise ValueError("IMAP config must contain [[account]] tables")
    accounts = []
    for raw in raw_accounts:
        if not isinstance(raw, dict):
            raise ValueError("Each IMAP account must be a table")
        accounts.append(
            ImapAccount(
                host=str(raw["host"]),
                username=str(raw["username"]),
                password_env=str(raw["password_env"]),
                trash_folder=str(raw["trash_folder"]),
                port=int(raw.get("port", 993)),
            )
        )
    return tuple(accounts)


def _path_contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _server_directory_from_pref(profile: Path, value: str) -> Path:
    normalized = value.replace("\\", "/")
    if normalized.startswith("[ProfD]"):
        return profile / normalized.removeprefix("[ProfD]").lstrip("/")
    return Path(normalized)


def _account_identity_from_prefs(
    profile: Path, account_directory: str, mbox_path: Path | None
) -> tuple[str, str] | None:
    prefs_path = profile / "prefs.js"
    try:
        lines = prefs_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    servers: dict[str, dict[str, str]] = {}
    for line in lines:
        match = _SERVER_PREF_RE.match(line)
        if not match:
            continue
        server, field, encoded_value = match.groups()
        try:
            value = json.loads(encoded_value)
        except json.JSONDecodeError:
            continue
        if isinstance(value, str):
            servers.setdefault(server, {})[field] = value
    identities = []
    for values in servers.values():
        directories = [
            _server_directory_from_pref(profile, values[field])
            for field in ("directory-rel", "directory")
            if field in values
        ]
        if not any(
            directory.name == account_directory
            or (mbox_path is not None and _path_contains(directory, mbox_path))
            for directory in directories
        ):
            continue
        host = values.get("hostname") or values.get("realhostname")
        username = values.get("userName")
        if host and username:
            identities.append((host, username))
    return identities[0] if len(identities) == 1 else None


def account_for_message(
    message: MailMessage, accounts: tuple[ImapAccount, ...]
) -> tuple[ImapAccount, str]:
    folder_uri = message.metadata.folder_uri if message.metadata else None
    account_directory = None
    identity = None
    if folder_uri:
        username, host, folder = parse_folder_uri(folder_uri)
        matches = [
            account
            for account in accounts
            if account.host.casefold() == host.casefold()
            and account.username.casefold() == username.casefold()
        ]
    else:
        # Gloda does not index every locally stored message. Fall back to the
        # Thunderbird ImapMail account directory, but only when its host maps
        # to exactly one configured account.
        account_location = next(
            (
                (parent.name, parent.parent.parent)
                for parent in (message.mbox_path.parents if message.mbox_path else ())
                if parent.parent.name == "ImapMail"
            ),
            None,
        )
        account_directory, profile = account_location or (None, None)
        identity = (
            _account_identity_from_prefs(profile, account_directory, message.mbox_path)
            if profile and account_directory
            else None
        )
        if identity:
            host, username = identity
            matches = [
                account
                for account in accounts
                if account.host.casefold() == host.casefold()
                and account.username.casefold() == username.casefold()
            ]
        else:
            matches = [
                account
                for account in accounts
                if account_directory
                and (
                    account_directory.casefold() == account.host.casefold()
                    or re.fullmatch(
                        rf"{re.escape(account.host)}-\d+",
                        account_directory,
                        flags=re.IGNORECASE,
                    )
                )
            ]
        folder = message.source_folder or ""
    if len(matches) != 1:
        detail = ""
        if folder_uri:
            detail = f" for folder URI {folder_uri!r}"
        elif account_directory:
            detail = f" for Thunderbird account directory {account_directory!r}"
            if identity:
                host, username = identity
                detail += f" mapped by prefs.js to {username}@{host}"
        raise ValueError(
            f"No unique configured IMAP account matches this message{detail}"
        )
    if not folder:
        raise ValueError("Message has no source IMAP folder")
    return matches[0], folder


def validate_move_candidate(
    message: MailMessage, accounts: tuple[ImapAccount, ...]
) -> tuple[ImapAccount, str]:
    """Resolve and validate every attacker-controlled IMAP command argument."""
    account, folder = account_for_message(message, accounts)
    if folder.casefold() == account.trash_folder.casefold():
        raise ValueError("Message is already in the configured Trash folder")
    _validated_message_id(message.header_message_id)
    _quoted_mailbox(folder)
    _quoted_mailbox(account.trash_folder)
    return account, folder


def _search_message_uids(
    connection: imaplib.IMAP4_SSL,
    message_id: str,
    *,
    gmail_extensions: bool,
) -> list[bytes]:
    if gmail_extensions:
        for candidate in (message_id, f"<{message_id}>"):
            status, data = connection.uid(
                "SEARCH",
                "X-GM-RAW",
                _quoted_mailbox(f"rfc822msgid:{candidate}"),
            )
            if status != "OK":
                raise RuntimeError("IMAP message search failed")
            uids = data[0].split() if data else []
            if uids:
                return uids
        return []
    else:
        status, data = connection.uid(
            "SEARCH",
            None,
            "HEADER",
            "Message-ID",
            _quoted_mailbox(f"<{message_id}>"),
        )
    if status != "OK":
        raise RuntimeError("IMAP message search failed")
    return data[0].split() if data else []


def _post_login_capabilities(connection: imaplib.IMAP4_SSL) -> set[str]:
    status, data = connection.capability()
    if status != "OK":
        raise RuntimeError("CAPABILITY query failed after login")
    return {
        capability.upper()
        for item in (data or ())
        for capability in (
            item.decode("ascii", errors="ignore")
            if isinstance(item, bytes)
            else str(item)
        ).split()
    }


def _all_mailbox(connection: imaplib.IMAP4_SSL) -> str:
    # imaplib's defaults emit the required `LIST "" *`. Passing a Python
    # empty string directly produces an empty command token that Gmail rejects.
    status, data = connection.list()
    if status != "OK":
        raise RuntimeError("Could not list IMAP mailboxes")
    matches = []
    for raw_item in data or ():
        item = (
            raw_item.decode("ascii", errors="ignore")
            if isinstance(raw_item, bytes)
            else str(raw_item)
        )
        match = _LIST_RESPONSE_RE.match(item)
        if not match:
            continue
        flags = {flag.upper() for flag in match.group("flags").split()}
        if r"\ALL" in flags:
            matches.append(match.group("mailbox"))
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one SPECIAL-USE All Mail mailbox, found {len(matches)}"
        )
    return matches[0]


def _locate_message_uids(
    connection: imaplib.IMAP4_SSL,
    folder: str,
    message_id: str,
    *,
    gmail_extensions: bool,
    readonly: bool,
) -> tuple[str, list[bytes]]:
    selected_folder = _quoted_mailbox(folder)
    status, _ = connection.select(selected_folder, readonly=readonly)
    if status != "OK":
        raise RuntimeError("Could not select the message folder")
    uids = _search_message_uids(
        connection,
        message_id,
        gmail_extensions=gmail_extensions,
    )
    if not uids and gmail_extensions:
        selected_folder = _all_mailbox(connection)
        status, _ = connection.select(selected_folder, readonly=readonly)
        if status != "OK":
            raise RuntimeError("Could not select the All Mail mailbox")
        uids = _search_message_uids(
            connection,
            message_id,
            gmail_extensions=True,
        )
    return selected_folder, uids


def _unexpected_match_count_message(count: int) -> str:
    if count == 0:
        return (
            "Message was not found on the IMAP server. The local Thunderbird "
            "snapshot is likely stale; refresh Thunderbird and the mail-assistant "
            "snapshot, then try again."
        )
    return f"Expected one IMAP message match, found {count}"


def verify_message_available_for_move(
    message: MailMessage,
    accounts: tuple[ImapAccount, ...],
    *,
    connector: Callable[..., imaplib.IMAP4_SSL] = imaplib.IMAP4_SSL,
) -> None:
    """Read-only preflight for creating a user-visible Trash proposal."""
    account, folder = validate_move_candidate(message, accounts)
    message_id = _validated_message_id(message.header_message_id)
    password = os.getenv(account.password_env)
    if not password:
        raise RuntimeError(
            f"Required password environment variable is unset: {account.password_env}"
        )
    connection = connector(
        account.host,
        account.port,
        ssl_context=ssl.create_default_context(),
        timeout=30,
    )
    try:
        status, _ = connection.login(account.username, password)
        if status != "OK":
            raise RuntimeError("IMAP login failed")
        capabilities = _post_login_capabilities(connection)
        if "MOVE" not in capabilities:
            raise RuntimeError("IMAP server does not support atomic MOVE")
        _, uids = _locate_message_uids(
            connection,
            folder,
            message_id,
            gmail_extensions="X-GM-EXT-1" in capabilities,
            readonly=True,
        )
        if len(uids) != 1:
            raise RuntimeError(_unexpected_match_count_message(len(uids)))
    finally:
        try:
            connection.logout()
        except Exception:
            pass


def move_message_to_trash(
    message: MailMessage,
    accounts: tuple[ImapAccount, ...],
    *,
    connector: Callable[..., imaplib.IMAP4_SSL] = imaplib.IMAP4_SSL,
    ) -> None:
    account, folder = validate_move_candidate(message, accounts)
    message_id = _validated_message_id(message.header_message_id)
    trash_folder = _quoted_mailbox(account.trash_folder)
    password = os.getenv(account.password_env)
    if not password:
        raise RuntimeError(f"Required password environment variable is unset: {account.password_env}")
    connection = connector(
        account.host,
        account.port,
        ssl_context=ssl.create_default_context(),
        timeout=30,
    )
    try:
        status, _ = connection.login(account.username, password)
        if status != "OK":
            raise RuntimeError("IMAP login failed")
        capabilities = _post_login_capabilities(connection)
        if "MOVE" not in capabilities:
            raise RuntimeError("IMAP server does not support atomic MOVE")
        gmail_extensions = "X-GM-EXT-1" in capabilities
        selected_folder, uids = _locate_message_uids(
            connection,
            folder,
            message_id,
            gmail_extensions=gmail_extensions,
            readonly=False,
        )
        if len(uids) != 1:
            raise RuntimeError(_unexpected_match_count_message(len(uids)))
        status, _ = connection.uid("MOVE", uids[0], trash_folder)
        if status != "OK":
            raise RuntimeError("IMAP MOVE failed")
    finally:
        try:
            connection.logout()
        except Exception:
            pass

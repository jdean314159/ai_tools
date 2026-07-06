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
    r'^user_pref\("mail\.server\.(server\d+)\.(directory-rel|hostname|userName)",\s*(.+)\);$'
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


def _account_identity_from_prefs(
    profile: Path, account_directory: str
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
        directory = values.get("directory-rel", "").replace("\\", "/")
        if directory.rsplit("/", 1)[-1] != account_directory:
            continue
        host = values.get("hostname")
        username = values.get("userName")
        if host and username:
            identities.append((host, username))
    return identities[0] if len(identities) == 1 else None


def account_for_message(
    message: MailMessage, accounts: tuple[ImapAccount, ...]
) -> tuple[ImapAccount, str]:
    folder_uri = message.metadata.folder_uri if message.metadata else None
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
            _account_identity_from_prefs(profile, account_directory)
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
        raise ValueError("No unique configured IMAP account matches this message")
    if not folder:
        raise ValueError("Message has no source IMAP folder")
    return matches[0], folder


def validate_move_candidate(
    message: MailMessage, accounts: tuple[ImapAccount, ...]
) -> tuple[ImapAccount, str]:
    """Resolve and validate every attacker-controlled IMAP command argument."""
    account, folder = account_for_message(message, accounts)
    _validated_message_id(message.header_message_id)
    _quoted_mailbox(folder)
    _quoted_mailbox(account.trash_folder)
    return account, folder


def move_message_to_trash(
    message: MailMessage,
    accounts: tuple[ImapAccount, ...],
    *,
    connector: Callable[..., imaplib.IMAP4_SSL] = imaplib.IMAP4_SSL,
) -> None:
    account, folder = validate_move_candidate(message, accounts)
    message_id = _validated_message_id(message.header_message_id)
    selected_folder = _quoted_mailbox(folder)
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
        capabilities = {
            item.decode("ascii", errors="ignore").upper()
            for item in connection.capabilities
        }
        if "MOVE" not in capabilities:
            raise RuntimeError("IMAP server does not support atomic MOVE")
        status, _ = connection.select(selected_folder, readonly=False)
        if status != "OK":
            raise RuntimeError("Could not select the message folder")
        status, data = connection.uid("SEARCH", None, "HEADER", "Message-ID", f"<{message_id}>")
        uids = data[0].split() if status == "OK" and data else []
        if len(uids) != 1:
            raise RuntimeError(f"Expected one IMAP message match, found {len(uids)}")
        status, _ = connection.uid("MOVE", uids[0], trash_folder)
        if status != "OK":
            raise RuntimeError("IMAP MOVE failed")
    finally:
        try:
            connection.logout()
        except Exception:
            pass

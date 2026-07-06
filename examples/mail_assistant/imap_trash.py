"""Explicit, confirmed IMAP move-to-trash support."""
from __future__ import annotations

from dataclasses import dataclass
import imaplib
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


def account_for_message(
    message: MailMessage, accounts: tuple[ImapAccount, ...]
) -> tuple[ImapAccount, str]:
    folder_uri = message.metadata.folder_uri if message.metadata else None
    if not folder_uri:
        raise ValueError("Message has no IMAP folder metadata")
    username, host, folder = parse_folder_uri(folder_uri)
    matches = [
        account
        for account in accounts
        if account.host.casefold() == host.casefold()
        and account.username.casefold() == username.casefold()
    ]
    if len(matches) != 1:
        raise ValueError("No unique configured IMAP account matches this message")
    if not folder:
        raise ValueError("Message has no source IMAP folder")
    return matches[0], folder


def move_message_to_trash(
    message: MailMessage,
    accounts: tuple[ImapAccount, ...],
    *,
    connector: Callable[..., imaplib.IMAP4_SSL] = imaplib.IMAP4_SSL,
) -> None:
    account, folder = account_for_message(message, accounts)
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

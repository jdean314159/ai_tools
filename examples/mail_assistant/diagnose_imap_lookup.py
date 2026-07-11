"""Read-only diagnosis for local-snapshot versus Gmail IMAP identity drift."""
from __future__ import annotations

import argparse
from email import policy
from email.parser import BytesParser
import imaplib
import os
from pathlib import Path
import sqlite3
import ssl

from ._bootstrap import install_repo_source_paths

install_repo_source_paths()

from .imap_trash import (  # noqa: E402
    ImapAccount,
    _all_mailbox,
    _quoted_mailbox,
    _validated_message_id,
    account_for_message,
    load_imap_accounts,
)
from .services import _decode_snapshot  # noqa: E402
from .store import DEFAULT_STORE_PATH  # noqa: E402


def _validated_subject(value: str) -> str:
    if not value or len(value) > 500:
        raise ValueError("Subject must contain 1-500 characters")
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("Diagnostic subject must contain ASCII characters only") from exc
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("Diagnostic subject must not contain control characters")
    if '"' in value or "\\" in value:
        raise ValueError("Diagnostic subject must not contain quote or backslash")
    return value


def _all_snapshot_messages(database: Path):
    uri = f"file:{database}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        row = connection.execute(
            "SELECT payload FROM mail_snapshot_cache LIMIT 1"
        ).fetchone()
    if row is None:
        raise RuntimeError("Mail-assistant snapshot cache is empty")
    return tuple(_decode_snapshot(row[0]))


def _snapshot_messages(database: Path, subject: str):
    return tuple(
        message
        for message in _all_snapshot_messages(database)
        if message.subject == subject
    )


def _print_subject_hints(database: Path, needle: str | None = None) -> None:
    messages = _all_snapshot_messages(database)
    if needle:
        lowered = needle.lower()
        messages = tuple(
            message for message in messages if lowered in message.subject.lower()
        )
    subjects = sorted({message.subject for message in messages})
    if not subjects:
        print("No cached subjects matched the supplied text.")
        return
    print("Cached subject candidates; copy one exactly into --subject:")
    for subject in subjects[:25]:
        print(f"  {subject!r}")
    if len(subjects) > 25:
        print(f"  ... {len(subjects) - 25} more omitted")


def _raw_search(connection: imaplib.IMAP4_SSL, query: str) -> list[bytes]:
    status, data = connection.uid("SEARCH", "X-GM-RAW", _quoted_mailbox(query))
    if status != "OK":
        raise RuntimeError(f"X-GM-RAW search failed: {status}")
    return data[0].split() if data else []


def _header_search(connection: imaplib.IMAP4_SSL, value: str) -> list[bytes]:
    status, data = connection.uid(
        "SEARCH",
        "HEADER",
        "Message-ID",
        _quoted_mailbox(value),
    )
    if status != "OK":
        raise RuntimeError(f"HEADER Message-ID search failed: {status}")
    return data[0].split() if data else []


def _header_fields(connection: imaplib.IMAP4_SSL, uid: bytes) -> tuple[str, str]:
    status, data = connection.uid(
        "FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID SUBJECT)])"
    )
    if status != "OK":
        raise RuntimeError(f"Header FETCH failed for UID {uid!r}: {status}")
    payload = next(
        (
            item[1]
            for item in data or ()
            if isinstance(item, tuple)
            and len(item) > 1
            and isinstance(item[1], bytes)
        ),
        None,
    )
    if payload is None:
        raise RuntimeError(f"Header FETCH returned no payload for UID {uid!r}")
    headers = BytesParser(policy=policy.default).parsebytes(payload, headersonly=True)
    return str(headers.get("Subject", "")), str(headers.get("Message-ID", ""))


def _probe_account(
    account: ImapAccount,
    subject: str | None,
    message_ids: set[str],
) -> None:
    password = os.getenv(account.password_env)
    print(
        f"\nACCOUNT host={account.host!r} username={account.username!r} "
        f"password_env={account.password_env!r}"
    )
    if not password:
        print("  SKIP: password environment variable is unset")
        return
    connection = imaplib.IMAP4_SSL(
        account.host,
        account.port,
        ssl_context=ssl.create_default_context(),
        timeout=30,
    )
    try:
        status, _ = connection.login(account.username, password)
        if status != "OK":
            raise RuntimeError("IMAP login failed")
        status, data = connection.capability()
        capabilities = {
            token.upper()
            for item in (data or ())
            for token in (
                item.decode("ascii", errors="ignore")
                if isinstance(item, bytes)
                else str(item)
            ).split()
        }
        if status != "OK" or "X-GM-EXT-1" not in capabilities:
            print("  SKIP: account does not advertise Gmail X-GM-EXT-1")
            return
        all_mail = _all_mailbox(connection)
        status, _ = connection.select(all_mail, readonly=True)
        if status != "OK":
            raise RuntimeError("Could not select SPECIAL-USE All Mail read-only")
        print(f"  all_mail={all_mail}")
        for message_id in sorted(message_ids):
            bare = _raw_search(connection, f"rfc822msgid:{message_id}")
            bracketed = _raw_search(connection, f"rfc822msgid:<{message_id}>")
            header_bracketed = _header_search(connection, f"<{message_id}>")
            header_bare = _header_search(connection, message_id)
            print(
                f"  snapshot_message_id={message_id!r} "
                f"bare_uids={[uid.decode('ascii', errors='replace') for uid in bare]} "
                f"bracketed_uids={[uid.decode('ascii', errors='replace') for uid in bracketed]} "
                f"header_bracketed_uids={[uid.decode('ascii', errors='replace') for uid in header_bracketed]} "
                f"header_bare_uids={[uid.decode('ascii', errors='replace') for uid in header_bare]}"
            )
        if subject is not None:
            subject_uids = _raw_search(connection, f'subject:"{subject}"')
            print(
                "  subject_search_uids="
                f"{[uid.decode('ascii', errors='replace') for uid in subject_uids]}"
            )
            for uid in subject_uids:
                server_subject, server_message_id = _header_fields(connection, uid)
                print(
                    f"  UID {uid.decode('ascii', errors='replace')}: "
                    f"Subject={server_subject!r} Message-ID={server_message_id!r}"
                )
    finally:
        try:
            connection.logout()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Gmail lookup diagnosis; prints subjects and Message-IDs only."
    )
    parser.add_argument("--subject")
    parser.add_argument(
        "--message-id",
        action="append",
        default=[],
        help="Probe one bare Message-ID directly; may be supplied multiple times.",
    )
    parser.add_argument(
        "--list-subjects",
        action="store_true",
        help="Print cached subjects, optionally filtered by --contains, then exit.",
    )
    parser.add_argument(
        "--contains",
        help="Case-insensitive subject substring for --list-subjects or no-match hints.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(os.getenv("MAIL_ASSISTANT_DB", DEFAULT_STORE_PATH)),
    )
    parser.add_argument(
        "--imap-accounts",
        type=Path,
        default=Path(
            os.getenv(
                "MAIL_ASSISTANT_IMAP_ACCOUNTS",
                Path.home() / ".config" / "mail_assistant" / "imap_accounts.toml",
            )
        ),
    )
    args = parser.parse_args()
    if args.list_subjects:
        _print_subject_hints(args.database, args.contains)
        return 0
    if not args.subject and not args.message_id:
        parser.error("--subject or --message-id is required unless --list-subjects is used")
    if args.subject == "Exact failing message subject":
        parser.error(
            "replace the placeholder with the actual subject text from the failing message"
        )
    subject = _validated_subject(args.subject) if args.subject else None
    accounts = load_imap_accounts(args.imap_accounts)
    messages = _snapshot_messages(args.database, subject) if subject else ()
    if subject and not messages:
        print("No cached snapshot message has that exact subject.")
        _print_subject_hints(args.database, args.contains or subject)
        return 2
    message_ids = {
        _validated_message_id(message_id) for message_id in args.message_id
    }
    message_ids.update(message.header_message_id for message in messages)
    if messages:
        print(f"SNAPSHOT exact_subject_matches={len(messages)}")
    for index, message in enumerate(messages, start=1):
        folder_uri = message.metadata.folder_uri if message.metadata else None
        try:
            account, folder = account_for_message(message, accounts)
            resolution = (
                f"host={account.host!r} username={account.username!r} folder={folder!r}"
            )
        except ValueError as exc:
            resolution = f"UNRESOLVED: {exc}"
        print(
            f"  [{index}] snapshot_message_id={message.header_message_id!r} "
            f"folder_uri={folder_uri!r} mbox_path={str(message.mbox_path)!r} "
            f"resolution={resolution}"
        )
    for account in accounts:
        _probe_account(account, subject, message_ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

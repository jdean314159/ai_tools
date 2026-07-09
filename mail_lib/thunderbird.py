"""Read Thunderbird Gloda metadata and extensionless mbox files.

The v0 reader is fixture-first and read-only. It iterates mbox messages as the
source of truth, then enriches by matching bracket-stripped Message-ID headers to
Gloda ``messages.headerMessageID`` rows. It never seeks by ``messageKey``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
import html
import json
import mailbox
from pathlib import Path
from urllib.parse import unquote, urlparse
import re
import sqlite3
from typing import Any, Iterable


ATTRIBUTE_FROM = 43
ATTRIBUTE_TO = 44
ATTRIBUTE_CC = 45
ATTRIBUTE_BCC = 46
ATTRIBUTE_INVOLVES = 52
ATTRIBUTE_RECIPIENTS = 53
ATTRIBUTE_FROM_ME = 54
ATTRIBUTE_TO_ME = 55
ATTRIBUTE_MAILING_LIST = 56
ATTRIBUTE_TAG = 57
ATTRIBUTE_STAR = 58
ATTRIBUTE_READ = 59
ATTRIBUTE_REPLIED_TO = 60
ATTRIBUTE_FORWARDED = 61


@dataclass(frozen=True)
class Identity:
    contact_id: int
    name: str
    address: str


@dataclass(frozen=True)
class MessageMetadata:
    header_message_id: str
    message_key: int | None
    folder_id: int | None
    conversation_id: int | None
    date: int | None
    sender_id: int | None
    recipient_ids: tuple[int, ...] = ()
    sender: Identity | None = None
    recipients: tuple[Identity, ...] = ()
    flags: dict[str, bool] = field(default_factory=dict)
    folder_uri: str | None = None
    folder_name: str | None = None


@dataclass(frozen=True)
class MailMessage:
    header_message_id: str
    subject: str
    body: str
    sender: str
    recipients: tuple[str, ...]
    date: str | None
    source_folder: str | None
    signal_folders: tuple[str, ...] = ()
    metadata: MessageMetadata | None = None
    mbox_path: Path | None = None
    local_read: bool = False
    read_state_source: str = "mbox"

    @property
    def has_gloda_metadata(self) -> bool:
        return self.metadata is not None


def normalize_message_id(value: str | None) -> str:
    """Normalize Message-ID values from mbox and Gloda for matching."""
    if not value:
        return ""
    return value.strip().strip("<>").strip()


def open_gloda_readonly(path: str | Path) -> sqlite3.Connection:
    """Open a Gloda fixture/database read-only with busy timeout."""
    db_path = Path(path)
    # Thunderbird may leave Gloda in exclusive locking mode even when it is not
    # running. Immutable mode bypasses those locks and guarantees this reader
    # cannot write to the profile; Gloda remains optional, lagging enrichment.
    conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=3000")
    return conn


def _gloda_path(profile_root: Path) -> Path:
    fixture = profile_root / "gloda_fixture.sqlite"
    if fixture.exists():
        return fixture
    return profile_root / "global-messages-db.sqlite"


def load_attribute_definitions(conn: sqlite3.Connection) -> dict[int, str]:
    rows = conn.execute("SELECT id, name FROM attributeDefinitions").fetchall()
    return {int(row["id"]): str(row["name"]) for row in rows}


def _parse_json_attributes(raw: str | bytes | None) -> dict[int, Any]:
    if not raw:
        return {}
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    data = json.loads(raw)
    return {int(key): value for key, value in data.items()}


def _as_id_tuple(value: Any) -> tuple[int, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(int(item) for item in value)
    return (int(value),)


def _as_bool(value: Any) -> bool:
    return bool(value) if isinstance(value, bool) else bool(value)


def _load_identities(conn: sqlite3.Connection) -> dict[int, Identity]:
    contacts = {
        int(row["id"]): str(row["name"] or "")
        for row in conn.execute("SELECT id, name FROM contacts")
    }
    identities: dict[int, Identity] = {}
    rows = conn.execute("SELECT contactID, kind, value FROM identities ORDER BY id").fetchall()
    for row in rows:
        contact_id = int(row["contactID"])
        kind = str(row["kind"] or "").lower()
        value = str(row["value"] or "")
        if contact_id in identities and kind != "email":
            continue
        identities[contact_id] = Identity(
            contact_id=contact_id,
            name=contacts.get(contact_id, ""),
            address=value,
        )
    return identities


def _load_folder_locations(conn: sqlite3.Connection) -> dict[int, tuple[str, str]]:
    rows = conn.execute("SELECT id, folderURI, name FROM folderLocations").fetchall()
    return {int(row["id"]): (str(row["folderURI"] or ""), str(row["name"] or "")) for row in rows}


def _cutoff_microseconds(newer_than: datetime | None) -> int | None:
    if newer_than is None:
        return None
    if newer_than.tzinfo is None:
        newer_than = newer_than.replace(tzinfo=timezone.utc)
    return int(newer_than.astimezone(timezone.utc).timestamp() * 1_000_000)


def load_gloda_metadata(
    profile_root: str | Path,
    *,
    newer_than: datetime | None = None,
) -> dict[str, MessageMetadata]:
    """Load Gloda metadata keyed by normalized header Message-ID."""
    db_path = _gloda_path(Path(profile_root))
    if not db_path.exists():
        return {}
    with open_gloda_readonly(db_path) as conn:
        identities = _load_identities(conn)
        folders = _load_folder_locations(conn)
        query = (
            "SELECT id, folderID, messageKey, conversationID, date, headerMessageID, "
            "deleted, jsonAttributes, notability FROM messages WHERE COALESCE(deleted, 0) = 0"
        )
        params: tuple[int, ...] = ()
        cutoff = _cutoff_microseconds(newer_than)
        if cutoff is not None:
            query += " AND date >= ?"
            params = (cutoff,)
        rows = conn.execute(query, params).fetchall()
        by_message_id: dict[str, MessageMetadata] = {}
        for row in rows:
            attrs = _parse_json_attributes(row["jsonAttributes"])
            sender_ids = _as_id_tuple(attrs.get(ATTRIBUTE_FROM))
            sender_id = sender_ids[0] if sender_ids else None
            recipient_ids = _as_id_tuple(attrs.get(ATTRIBUTE_TO)) + _as_id_tuple(attrs.get(ATTRIBUTE_RECIPIENTS))
            recipient_ids = tuple(dict.fromkeys(recipient_ids))
            folder_id = int(row["folderID"]) if row["folderID"] is not None else None
            folder_uri, folder_name = folders.get(folder_id or -1, ("", ""))
            flags = {
                "from_me": _as_bool(attrs.get(ATTRIBUTE_FROM_ME, False)),
                "to_me": _as_bool(attrs.get(ATTRIBUTE_TO_ME, False)),
                "mailing_list": _as_bool(attrs.get(ATTRIBUTE_MAILING_LIST, False)),
                "star": _as_bool(attrs.get(ATTRIBUTE_STAR, False)),
                "read": _as_bool(attrs.get(ATTRIBUTE_READ, False)),
                "replied": _as_bool(attrs.get(ATTRIBUTE_REPLIED_TO, False)),
                "forwarded": _as_bool(attrs.get(ATTRIBUTE_FORWARDED, False)),
            }
            header_id = normalize_message_id(str(row["headerMessageID"] or ""))
            if not header_id:
                continue
            metadata = MessageMetadata(
                header_message_id=header_id,
                message_key=int(row["messageKey"]) if row["messageKey"] is not None else None,
                folder_id=folder_id,
                conversation_id=int(row["conversationID"]) if row["conversationID"] is not None else None,
                date=int(row["date"]) if row["date"] is not None else None,
                sender_id=sender_id,
                recipient_ids=recipient_ids,
                sender=identities.get(sender_id) if sender_id is not None else None,
                recipients=tuple(identities[item] for item in recipient_ids if item in identities),
                flags=flags,
                folder_uri=folder_uri or None,
                folder_name=folder_name or None,
            )
            by_message_id[header_id] = metadata
        return by_message_id


def load_folder_tree(profile_root: str | Path) -> list[str]:
    path = Path(profile_root) / "folderTree.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    open_section = data.get("open", {})
    values = open_section.get("all", [])
    uris: list[str] = []
    for item in values:
        if isinstance(item, str):
            uris.append(item)
        elif isinstance(item, dict):
            uri = item.get("uri") or item.get("folderURI")
            if uri:
                uris.append(str(uri))
    return uris


def parse_folder_uri(uri: str) -> tuple[str, str, str]:
    parsed = urlparse(uri)
    account = unquote(parsed.username or "")
    host = parsed.hostname or ""
    folder_path = unquote(parsed.path.lstrip("/"))
    return account, host, folder_path


def discover_mbox_files(profile_root: str | Path) -> list[Path]:
    """Find extensionless Thunderbird mbox files marked by same-named .msf siblings."""
    root = Path(profile_root)
    mail_roots = [root / "ImapMail", root / "Mail"]
    found: list[Path] = []
    for mail_root in mail_roots:
        if not mail_root.exists():
            continue
        for path in mail_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix == ".msf":
                continue
            if path.with_name(path.name + ".msf").exists():
                found.append(path)
    return sorted(found)


def _message_body(message: Message) -> str:
    if message.is_multipart():
        html_part = ""
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disposition:
                continue
            payload = _decode_part(part)
            if content_type == "text/plain" and payload.strip():
                return payload
            if content_type == "text/html" and payload.strip() and not html_part:
                html_part = _html_to_text(payload)
        return html_part
    if message.get_content_type() == "text/html":
        return _html_to_text(_decode_part(message))
    return _decode_part(message)


def _decode_part(message: Message) -> str:
    payload = message.get_payload(decode=True)
    charset = message.get_content_charset() or "utf-8"
    if payload is None:
        text = message.get_payload()
        return text if isinstance(text, str) else ""
    return payload.decode(charset, errors="replace")


_TAG_RE = re.compile(r"<[^>]+>")
_HREF_RE = re.compile(r"""<a\b[^>]*\bhref\s*=\s*["']([^"']+)["'][^>]*>""", re.IGNORECASE)


def _html_to_text(text: str) -> str:
    """Convert HTML to visible text, preserving anchor href URLs.

    Tag stripping alone discards <a href="..."> targets, which silently loses
    URLs that are only present as link destinations (common in mail shared from
    a phone). Append each http(s) href so the URL survives in the body text.
    """
    hrefs = [
        unescaped
        for raw in _HREF_RE.findall(text)
        if (unescaped := html.unescape(raw)).lower().startswith(("http://", "https://"))
    ]
    stripped = html.unescape(_TAG_RE.sub(" ", text)).strip()
    if not hrefs:
        return stripped
    appended = " ".join(hrefs)
    return f"{stripped} {appended}".strip()


def _addresses(header_value: str | None) -> tuple[str, ...]:
    return tuple(address for _name, address in getaddresses([header_value or ""]) if address)


def _message_date(message: Message) -> str | None:
    parsed = _message_datetime(message)
    if parsed is not None:
        return parsed.isoformat()
    raw = message.get("Date")
    return str(raw) if raw else None


def _message_datetime(message: Message) -> datetime | None:
    raw = message.get("Date")
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _mozilla_read(message: Message) -> bool:
    raw = str(message.get("X-Mozilla-Status") or "").strip()
    try:
        return bool(int(raw, 16) & 0x0001)
    except ValueError:
        return False


_MORK_ALIAS_RE = re.compile(r"\(([0-9A-F]+)\s*=([^)]*)\)", re.DOTALL)
_MORK_CELL_RE = re.compile(r"\(\^?([0-9A-F]+)(?:=([^)]*)|\^([0-9A-F]+))\)")
_MORK_ROW_RE = re.compile(r"\[-?[0-9A-F]+(?::(?:\^80|m))?(.*?)\]", re.DOTALL)
_MORK_MESSAGE_ID_FIELD = "83"
_MORK_FLAGS_FIELD = "88"
_THUNDERBIRD_READ_FLAG = 0x0001


def _decode_mork_value(value: str) -> str:
    return value.replace("\\\n", "").replace("\\)", ")").replace("\\\\", "\\")


def load_msf_read_states(msf_path: str | Path) -> dict[str, bool]:
    """Load Thunderbird .msf read flags keyed by normalized Message-ID.

    Thunderbird's Gloda database can lag behind the UI, and the mbox
    ``X-Mozilla-Status`` header can also be stale for IMAP folders. The sibling
    ``.msf`` summary is the source Thunderbird updates while displaying folder
    state. This intentionally parses only the small Mork subset needed for
    message rows: ``message-id`` and ``flags``.
    """
    path = Path(msf_path)
    if not path.exists():
        return {}
    text = path.read_text(errors="replace").replace("\\\n", "")
    aliases = {
        key.upper(): _decode_mork_value(value)
        for key, value in _MORK_ALIAS_RE.findall(text)
    }
    read_by_id: dict[str, bool] = {}
    for row in _MORK_ROW_RE.finditer(text):
        row_block = row.group(1)
        cells: dict[str, str] = {}
        for key, raw_value, alias_key in _MORK_CELL_RE.findall(row_block):
            key = key.upper()
            if alias_key:
                value = aliases.get(alias_key.upper(), alias_key)
            else:
                value = raw_value
            cells[key] = _decode_mork_value(value)
        message_id = normalize_message_id(cells.get(_MORK_MESSAGE_ID_FIELD))
        flags = cells.get(_MORK_FLAGS_FIELD)
        if not message_id or flags is None:
            continue
        try:
            read_by_id[message_id] = bool(int(flags, 16) & _THUNDERBIRD_READ_FLAG)
        except ValueError:
            continue
    return read_by_id


def _folder_label(path: Path) -> str:
    parts: list[str] = []
    current = path
    while current.parent.name.endswith(".sbd"):
        parts.append(current.name)
        current = current.parent.with_suffix("")
    parts.append(current.name)
    return "/".join(reversed(parts))


def _is_source_folder(label: str) -> bool:
    normalized = label.lower()
    return normalized.endswith("all mail") or normalized == "inbox"


def _message_from_mbox(
    message: Message,
    *,
    mbox_path: Path,
    folder_label: str,
    metadata: MessageMetadata | None,
    msf_read: bool | None = None,
) -> MailMessage | None:
    header_id = normalize_message_id(message.get("Message-ID"))
    if not header_id:
        return None
    sender = metadata.sender.address if metadata and metadata.sender else (_addresses(message.get("From")) or ("",))[0]
    recipients = tuple(item.address for item in metadata.recipients) if metadata and metadata.recipients else _addresses(message.get("To"))
    local_read = _mozilla_read(message) if msf_read is None else msf_read
    return MailMessage(
        header_message_id=header_id,
        subject=str(message.get("Subject") or ""),
        body=_message_body(message),
        sender=sender,
        recipients=recipients,
        date=_message_date(message),
        source_folder=folder_label if _is_source_folder(folder_label) else None,
        signal_folders=() if _is_source_folder(folder_label) else (folder_label,),
        metadata=metadata,
        mbox_path=mbox_path,
        local_read=local_read,
        read_state_source="mbox" if msf_read is None else "msf",
    )


def _merge_messages(existing: MailMessage, new: MailMessage) -> MailMessage:
    source_folder = existing.source_folder or new.source_folder
    signals = tuple(dict.fromkeys(existing.signal_folders + new.signal_folders))
    metadata = existing.metadata or new.metadata
    body_source = existing if existing.body else new
    if existing.read_state_source == "msf" and new.read_state_source == "msf":
        local_read = existing.local_read and new.local_read
        read_state_source = "msf"
    elif existing.read_state_source == "msf":
        local_read = existing.local_read
        read_state_source = "msf"
    elif new.read_state_source == "msf":
        local_read = new.local_read
        read_state_source = "msf"
    else:
        local_read = existing.local_read and new.local_read
        read_state_source = existing.read_state_source
    return MailMessage(
        header_message_id=existing.header_message_id,
        subject=body_source.subject,
        body=body_source.body,
        sender=existing.sender or new.sender,
        recipients=existing.recipients or new.recipients,
        date=existing.date or new.date,
        source_folder=source_folder,
        signal_folders=signals,
        metadata=metadata,
        mbox_path=body_source.mbox_path,
        local_read=local_read,
        read_state_source=read_state_source,
    )


def iter_messages(
    profile_root: str | Path,
    *,
    newer_than: datetime | None = None,
) -> Iterable[MailMessage]:
    """Yield deduplicated mbox messages enriched with Gloda metadata when present."""
    root = Path(profile_root)
    cutoff = newer_than
    if cutoff is not None and cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    if cutoff is not None:
        cutoff = cutoff.astimezone(timezone.utc)
    metadata_by_id = load_gloda_metadata(root, newer_than=cutoff)
    messages: dict[str, MailMessage] = {}
    for mbox_path in discover_mbox_files(root):
        folder_label = _folder_label(mbox_path)
        msf_read_by_id = load_msf_read_states(mbox_path.with_name(mbox_path.name + ".msf"))
        box = mailbox.mbox(mbox_path, create=False)
        try:
            for message in box:
                message_dt = _message_datetime(message)
                if cutoff is not None and (message_dt is None or message_dt < cutoff):
                    continue
                header_id = normalize_message_id(message.get("Message-ID"))
                metadata = metadata_by_id.get(header_id)
                mail_message = _message_from_mbox(
                    message,
                    mbox_path=mbox_path,
                    folder_label=folder_label,
                    metadata=metadata,
                    msf_read=msf_read_by_id.get(header_id),
                )
                if mail_message is None:
                    continue
                if header_id in messages:
                    messages[header_id] = _merge_messages(messages[header_id], mail_message)
                else:
                    messages[header_id] = mail_message
        finally:
            box.close()
    return list(messages.values())

#!/usr/bin/env python3
"""Build a provenance-preserving normalized corpus from a Claude export."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ANSI_ESCAPE_RE = re.compile(
    r"""
    \x1B
    (?:
        [@-_]
        |
        \[
        [0-?]*
        [ -/]*
        [@-~]
    )
    """,
    re.VERBOSE,
)
TRAILING_HORIZONTAL_RE = re.compile(r"[ \t]+$", re.MULTILINE)
EXCESS_BLANK_LINES_RE = re.compile(r"\n{4,}")
REMOVED_FORMAT_CHARACTERS = {"\u200b", "\ufeff"}
EXPECTED_EXPORT_SHA256 = (
    "368787d2020d97f962bc4f773e550a07bda5ffe3f1b2510fdbe84a8b36ef4735"
)
EARLIEST_BENCHMARK_DECISION = "2026-05-22T00:00:00Z"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(encoded)


def normalize_text(raw: str) -> tuple[str, dict[str, int]]:
    counts: Counter[str] = Counter()
    text = raw

    crlf_count = text.count("\r\n")
    if crlf_count:
        counts["crlf_to_lf"] += crlf_count
        text = text.replace("\r\n", "\n")
    cr_count = text.count("\r")
    if cr_count:
        counts["cr_to_lf"] += cr_count
        text = text.replace("\r", "\n")

    normalized = unicodedata.normalize("NFC", text)
    if normalized != text:
        counts["unicode_nfc"] += 1
        text = normalized

    text, ansi_count = ANSI_ESCAPE_RE.subn("", text)
    if ansi_count:
        counts["ansi_escape_removed"] += ansi_count

    nbsp_count = text.count("\u00a0")
    if nbsp_count:
        counts["nbsp_to_space"] += nbsp_count
        text = text.replace("\u00a0", " ")

    separator_count = text.count("\u2028") + text.count("\u2029")
    if separator_count:
        counts["unicode_separator_to_lf"] += separator_count
        text = text.replace("\u2028", "\n").replace("\u2029", "\n")

    filtered: list[str] = []
    removed_controls = 0
    removed_formats = 0
    for char in text:
        category = unicodedata.category(char)
        if category == "Cc" and char not in "\n\t":
            removed_controls += 1
            continue
        if char in REMOVED_FORMAT_CHARACTERS:
            removed_formats += 1
            continue
        filtered.append(char)
    if removed_controls:
        counts["control_characters_removed"] += removed_controls
    if removed_formats:
        counts["format_characters_removed"] += removed_formats
    text = "".join(filtered)

    text, trailing_count = TRAILING_HORIZONTAL_RE.subn("", text)
    if trailing_count:
        counts["trailing_whitespace_trimmed"] += trailing_count

    text, blank_count = EXCESS_BLANK_LINES_RE.subn("\n\n\n", text)
    if blank_count:
        counts["blank_line_runs_collapsed"] += blank_count

    stripped = text.strip(" \t\n")
    if stripped != text:
        counts["outer_whitespace_trimmed"] += 1
        text = stripped

    return text, dict(sorted(counts.items()))


def observe_text(text: str) -> dict[str, int]:
    observations: Counter[str] = Counter()
    for char in text:
        codepoint = ord(char)
        category = unicodedata.category(char)
        if codepoint > 127:
            observations["non_ascii_characters"] += 1
        if codepoint == 0xFFFD:
            observations["replacement_characters"] += 1
        if category == "Co":
            observations["private_use_characters"] += 1
        if category == "Cf":
            observations["format_characters_preserved"] += 1
    return dict(sorted(observations.items()))


def _parent_status(
    message_index: int,
    parent_uuid: str | None,
    message_ids: set[str],
) -> str:
    if parent_uuid is None:
        return "root"
    if parent_uuid in message_ids:
        return "present"
    if message_index == 0:
        return "external_root"
    return "orphaned"


def _record(
    *,
    conversation_uuid: str,
    message: dict[str, Any],
    message_index: int,
    message_ids: set[str],
    source_kind: str,
    source_index: int | None,
    raw_text: str,
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    normalized_text, operations = normalize_text(raw_text)
    if not normalized_text:
        return None
    parent_uuid = message.get("parent_message_uuid")
    record = {
        "schema_version": 1,
        "conversation_uuid": conversation_uuid,
        "message_uuid": message["uuid"],
        "parent_message_uuid": parent_uuid,
        "parent_status": _parent_status(
            message_index,
            parent_uuid,
            message_ids,
        ),
        "sender": message.get("sender"),
        "created_at": message.get("created_at"),
        "updated_at": message.get("updated_at"),
        "message_index": message_index,
        "source_kind": source_kind,
        "source_index": source_index,
        "raw_sha256": sha256_text(raw_text),
        "normalized_sha256": sha256_text(normalized_text),
        "raw_characters": len(raw_text),
        "normalized_characters": len(normalized_text),
        "normalizations": operations,
        "text_observations": observe_text(normalized_text),
        "normalized_text": normalized_text,
    }
    if source_metadata:
        record["source_metadata"] = source_metadata
    return record


def iter_records(conversation: dict[str, Any]) -> Iterable[dict[str, Any]]:
    conversation_uuid = conversation["uuid"]
    messages = conversation["chat_messages"]
    message_ids = {message["uuid"] for message in messages}
    for message_index, message in enumerate(messages):
        text = message.get("text")
        if isinstance(text, str) and text.strip():
            record = _record(
                conversation_uuid=conversation_uuid,
                message=message,
                message_index=message_index,
                message_ids=message_ids,
                source_kind="message_text",
                source_index=None,
                raw_text=text,
            )
            if record:
                yield record

        for attachment_index, attachment in enumerate(message.get("attachments", [])):
            if not isinstance(attachment, dict):
                continue
            extracted = attachment.get("extracted_content")
            if not isinstance(extracted, str) or not extracted.strip():
                continue
            record = _record(
                conversation_uuid=conversation_uuid,
                message=message,
                message_index=message_index,
                message_ids=message_ids,
                source_kind="attachment_extracted_content",
                source_index=attachment_index,
                raw_text=extracted,
                source_metadata={
                    "file_type": attachment.get("file_type") or "<missing>",
                },
            )
            if record:
                yield record


def load_selection(path: Path) -> dict[str, Any]:
    selection = json.loads(path.read_text(encoding="utf-8"))
    conversations = selection.get("conversations")
    if not isinstance(conversations, list) or len(conversations) != 10:
        raise ValueError("Selection must contain exactly ten conversations")
    ids = [item.get("conversation_uuid") for item in conversations]
    if not all(isinstance(item, str) and item for item in ids):
        raise ValueError("Every selection entry must contain a conversation UUID")
    if len(set(ids)) != len(ids):
        raise ValueError("Selection contains duplicate conversation UUIDs")
    return selection


def build_corpus(
    export_path: Path,
    selection_path: Path,
    output_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    export_hash = sha256_file(export_path)
    if export_hash != EXPECTED_EXPORT_SHA256:
        raise ValueError(
            "Export hash differs from the Phase 2 audited export; "
            "audit and version the new export before normalization"
        )

    selection = load_selection(selection_path)
    selected_ids = [
        item["conversation_uuid"] for item in selection["conversations"]
    ]
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    conversations_by_id = {
        conversation.get("uuid"): conversation
        for conversation in payload
        if isinstance(conversation, dict)
    }
    missing = [item for item in selected_ids if item not in conversations_by_id]
    if missing:
        raise ValueError(f"Selected conversation UUIDs missing from export: {len(missing)}")

    for conversation_uuid in selected_ids:
        created_at = conversations_by_id[conversation_uuid].get("created_at")
        if not isinstance(created_at, str) or created_at >= EARLIEST_BENCHMARK_DECISION:
            raise ValueError(
                "Selected conversations must predate the earliest benchmark decision"
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    record_count = 0
    source_counts: Counter[str] = Counter()
    sender_counts: Counter[str] = Counter()
    parent_counts: Counter[str] = Counter()
    operation_counts: Counter[str] = Counter()
    observation_counts: Counter[str] = Counter()
    raw_characters = 0
    normalized_characters = 0
    records_per_conversation: Counter[str] = Counter()

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for conversation_uuid in selected_ids:
            conversation = conversations_by_id[conversation_uuid]
            for record in iter_records(conversation):
                handle.write(
                    json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                )
                record_count += 1
                source_counts[record["source_kind"]] += 1
                sender_counts[str(record["sender"])] += 1
                parent_counts[record["parent_status"]] += 1
                records_per_conversation[conversation_uuid] += 1
                raw_characters += record["raw_characters"]
                normalized_characters += record["normalized_characters"]
                operation_counts.update(record["normalizations"])
                observation_counts.update(record["text_observations"])

    manifest = {
        "manifest_version": 1,
        "selection_version": selection["selection_version"],
        "export_sha256": export_hash,
        "selection_sha256": canonical_json_hash(selection),
        "normalized_corpus_sha256": sha256_file(output_path),
        "conversation_count": len(selected_ids),
        "conversation_uuids": selected_ids,
        "record_count": record_count,
        "source_counts": dict(sorted(source_counts.items())),
        "sender_counts": dict(sorted(sender_counts.items())),
        "parent_status_counts": dict(sorted(parent_counts.items())),
        "records_per_conversation": dict(sorted(records_per_conversation.items())),
        "raw_characters": raw_characters,
        "normalized_characters": normalized_characters,
        "normalization_counts": dict(sorted(operation_counts.items())),
        "text_observation_counts": dict(sorted(observation_counts.items())),
        "contains_private_text": False,
        "normalized_corpus_is_private": True,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the frozen normalized corpus for the knowledge MVP."
    )
    parser.add_argument("export", type=Path)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = build_corpus(
            args.export,
            args.selection,
            args.output,
            args.manifest,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"Corpus normalization failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Normalized corpus built: "
        f"{manifest['conversation_count']} conversations, "
        f"{manifest['record_count']} records, "
        f"sha256={manifest['normalized_corpus_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

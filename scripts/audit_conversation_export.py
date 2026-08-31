#!/usr/bin/env python3
"""Audit a Claude conversations export without emitting private content."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


EXPECTED_CONVERSATION_FIELDS = {
    "account",
    "chat_messages",
    "created_at",
    "name",
    "summary",
    "updated_at",
    "uuid",
}
EXPECTED_MESSAGE_FIELDS = {
    "attachments",
    "content",
    "created_at",
    "files",
    "parent_message_uuid",
    "sender",
    "text",
    "updated_at",
    "uuid",
}
VALID_SENDERS = {"assistant", "human"}
TEXT_BEARING_KEYS = {
    "content",
    "display_content",
    "extracted_content",
    "file_text",
    "message",
    "summaries",
    "text",
    "thinking",
}


@dataclass
class UnicodeStats:
    characters: int = 0
    non_ascii: int = 0
    controls: int = 0
    format_characters: int = 0
    private_use: int = 0
    replacement_characters: int = 0
    unpaired_surrogates: int = 0
    line_separators: int = 0
    paragraph_separators: int = 0
    categories: Counter[str] = field(default_factory=Counter)

    def observe(self, text: str) -> None:
        self.characters += len(text)
        for char in text:
            codepoint = ord(char)
            if codepoint > 127:
                self.non_ascii += 1
                self.categories[unicodedata.category(char)] += 1
            category = unicodedata.category(char)
            if category == "Cc" and char not in "\n\r\t":
                self.controls += 1
            elif category == "Cf":
                self.format_characters += 1
            elif category == "Co":
                self.private_use += 1
            elif category == "Zl":
                self.line_separators += 1
            elif category == "Zp":
                self.paragraph_separators += 1
            if codepoint == 0xFFFD:
                self.replacement_characters += 1
            if 0xD800 <= codepoint <= 0xDFFF:
                self.unpaired_surrogates += 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "characters": self.characters,
            "non_ascii": self.non_ascii,
            "controls_excluding_newline_tab": self.controls,
            "format_characters": self.format_characters,
            "private_use": self.private_use,
            "replacement_characters": self.replacement_characters,
            "unpaired_surrogates": self.unpaired_surrogates,
            "line_separators": self.line_separators,
            "paragraph_separators": self.paragraph_separators,
            "non_ascii_categories": dict(sorted(self.categories.items())),
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def iter_objects(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_objects(child)


def iter_text_values(value: Any, *, key: str | None = None) -> Iterable[str]:
    if isinstance(value, str):
        if key in TEXT_BEARING_KEYS:
            yield value
        return
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from iter_text_values(child, key=child_key)
    elif isinstance(value, list):
        for child in value:
            yield from iter_text_values(child, key=key)


def _cycle_count(parent_by_id: dict[str, str | None]) -> int:
    completed: set[str] = set()
    cycles: set[frozenset[str]] = set()
    for start in parent_by_id:
        if start in completed:
            continue
        path: list[str] = []
        positions: dict[str, int] = {}
        current: str | None = start
        while current is not None and current in parent_by_id:
            if current in positions:
                cycles.add(frozenset(path[positions[current] :]))
                break
            if current in completed:
                break
            positions[current] = len(path)
            path.append(current)
            current = parent_by_id[current]
        completed.update(path)
    return len(cycles)


def _integrity_status(errors: int, warnings: int) -> str:
    if errors:
        return "fail"
    if warnings:
        return "pass_with_warnings"
    return "pass"


def audit_export(path: Path) -> dict[str, Any]:
    source = {
        "file_name": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "schema_version": 1,
            "source": source,
            "status": "fail",
            "errors": [{"code": "unreadable_json", "count": 1}],
            "warnings": [],
            "parse_error": type(exc).__name__,
        }

    error_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    conversation_fields: Counter[str] = Counter()
    message_fields: Counter[str] = Counter()
    content_types: Counter[str] = Counter()
    sender_counts: Counter[str] = Counter()
    marker_counts: Counter[str] = Counter()
    attachment_types: Counter[str] = Counter()
    text_locations: Counter[str] = Counter()
    unicode_stats = UnicodeStats()

    if not isinstance(payload, list):
        error_counts["top_level_not_array"] += 1
        payload = []

    conversation_ids: Counter[str] = Counter()
    message_ids: Counter[str] = Counter()
    message_owner: dict[str, int] = {}
    parent_records: list[tuple[int, int, str, str | None]] = []
    created_values: list[datetime] = []
    updated_values: list[datetime] = []
    total_messages = 0
    total_attachments = 0
    total_files = 0
    messages_with_attachments = 0
    messages_with_files = 0

    for conversation_index, conversation in enumerate(payload):
        if not isinstance(conversation, dict):
            error_counts["conversation_not_object"] += 1
            continue
        conversation_fields.update(conversation.keys())
        missing_fields = EXPECTED_CONVERSATION_FIELDS - conversation.keys()
        if missing_fields:
            error_counts["conversation_missing_expected_fields"] += 1

        conversation_id = conversation.get("uuid")
        if isinstance(conversation_id, str) and conversation_id:
            conversation_ids[conversation_id] += 1
        else:
            error_counts["conversation_missing_uuid"] += 1

        for field_name, target in (
            ("created_at", created_values),
            ("updated_at", updated_values),
        ):
            parsed = parse_timestamp(conversation.get(field_name))
            if parsed is None:
                error_counts[f"conversation_invalid_{field_name}"] += 1
            else:
                target.append(parsed)

        messages = conversation.get("chat_messages")
        if not isinstance(messages, list):
            error_counts["chat_messages_not_array"] += 1
            continue

        local_ids: set[str] = set()
        local_parents: dict[str, str | None] = {}
        for message_index, message in enumerate(messages):
            total_messages += 1
            if not isinstance(message, dict):
                error_counts["message_not_object"] += 1
                continue
            message_fields.update(message.keys())
            if EXPECTED_MESSAGE_FIELDS - message.keys():
                error_counts["message_missing_expected_fields"] += 1

            message_id = message.get("uuid")
            valid_message_id = isinstance(message_id, str) and bool(message_id)
            if valid_message_id:
                message_ids[message_id] += 1
                local_ids.add(message_id)
                message_owner.setdefault(message_id, conversation_index)
            else:
                error_counts["message_missing_uuid"] += 1

            parent = message.get("parent_message_uuid")
            if parent is not None and not isinstance(parent, str):
                error_counts["parent_uuid_invalid_type"] += 1
                parent = None
            if valid_message_id:
                local_parents[message_id] = parent
                parent_records.append((conversation_index, message_index, message_id, parent))

            sender = message.get("sender")
            if isinstance(sender, str):
                sender_counts[sender] += 1
                if sender not in VALID_SENDERS:
                    warning_counts["unexpected_sender"] += 1
            else:
                error_counts["sender_invalid_type"] += 1

            created = parse_timestamp(message.get("created_at"))
            updated = parse_timestamp(message.get("updated_at"))
            if created is None:
                error_counts["message_invalid_created_at"] += 1
            else:
                created_values.append(created)
            if updated is None:
                error_counts["message_invalid_updated_at"] += 1
            else:
                updated_values.append(updated)
            if created is not None and updated is not None and updated < created:
                warning_counts["updated_before_created"] += 1

            text = message.get("text")
            if not isinstance(text, str):
                error_counts["message_text_not_string"] += 1
            else:
                text_locations["message_text"] += 1
                unicode_stats.observe(text)

            content = message.get("content")
            if not isinstance(content, list):
                error_counts["content_not_array"] += 1
            else:
                for block in content:
                    if not isinstance(block, dict):
                        error_counts["content_block_not_object"] += 1
                        continue
                    block_type = block.get("type")
                    if isinstance(block_type, str) and block_type:
                        content_types[block_type] += 1
                    else:
                        error_counts["content_block_missing_type"] += 1
                    for nested in iter_objects(block):
                        if nested.get("truncated") is True:
                            marker_counts["truncated_true"] += 1
                        if nested.get("cut_off") is True:
                            marker_counts["cut_off_true"] += 1
                    for nested_text in iter_text_values(block):
                        text_locations["content_blocks"] += 1
                        unicode_stats.observe(nested_text)

            attachments = message.get("attachments")
            if not isinstance(attachments, list):
                error_counts["attachments_not_array"] += 1
            else:
                total_attachments += len(attachments)
                messages_with_attachments += bool(attachments)
                for attachment in attachments:
                    if not isinstance(attachment, dict):
                        error_counts["attachment_not_object"] += 1
                        continue
                    file_type = attachment.get("file_type")
                    attachment_types[str(file_type or "<missing>")] += 1
                    extracted = attachment.get("extracted_content")
                    if extracted is not None and not isinstance(extracted, str):
                        error_counts["attachment_content_not_string"] += 1
                    elif isinstance(extracted, str):
                        text_locations["attachment_extracted_content"] += 1
                        unicode_stats.observe(extracted)

            files = message.get("files")
            if not isinstance(files, list):
                error_counts["files_not_array"] += 1
            else:
                total_files += len(files)
                messages_with_files += bool(files)
                for file_record in files:
                    if not isinstance(file_record, dict):
                        error_counts["file_record_not_object"] += 1
                    elif not isinstance(file_record.get("file_uuid"), str):
                        warning_counts["file_record_missing_uuid"] += 1

        parent_cycles = _cycle_count(local_parents)
        if parent_cycles:
            error_counts["parent_cycles"] += parent_cycles

    duplicate_conversations = sum(count - 1 for count in conversation_ids.values() if count > 1)
    duplicate_messages = sum(count - 1 for count in message_ids.values() if count > 1)
    if duplicate_conversations:
        error_counts["duplicate_conversation_uuids"] += duplicate_conversations
    if duplicate_messages:
        error_counts["duplicate_message_uuids"] += duplicate_messages

    missing_parents = 0
    external_root_parents = 0
    orphaned_parent_references = 0
    cross_conversation_parents = 0
    self_parents = 0
    for owner, message_index, message_id, parent in parent_records:
        if parent is None:
            continue
        if parent == message_id:
            self_parents += 1
        elif parent not in message_ids:
            missing_parents += 1
            if message_index == 0:
                external_root_parents += 1
            else:
                orphaned_parent_references += 1
        elif message_owner.get(parent) != owner:
            cross_conversation_parents += 1
    if external_root_parents:
        warning_counts["external_root_parent_references"] += external_root_parents
    if orphaned_parent_references:
        warning_counts["orphaned_parent_references"] += orphaned_parent_references
    if cross_conversation_parents:
        error_counts["cross_conversation_parent_references"] += cross_conversation_parents
    if self_parents:
        error_counts["self_parent_references"] += self_parents

    unknown_conversation_fields = sorted(set(conversation_fields) - EXPECTED_CONVERSATION_FIELDS)
    unknown_message_fields = sorted(set(message_fields) - EXPECTED_MESSAGE_FIELDS)
    if unknown_conversation_fields:
        warning_counts["unknown_conversation_fields"] += len(unknown_conversation_fields)
    if unknown_message_fields:
        warning_counts["unknown_message_fields"] += len(unknown_message_fields)
    if marker_counts:
        warning_counts["explicit_truncation_markers"] += sum(marker_counts.values())
    if unicode_stats.controls:
        warning_counts["embedded_control_characters"] += unicode_stats.controls
    if unicode_stats.replacement_characters:
        warning_counts["unicode_replacement_characters"] += unicode_stats.replacement_characters
    if unicode_stats.unpaired_surrogates:
        error_counts["unpaired_unicode_surrogates"] += unicode_stats.unpaired_surrogates

    report = {
        "schema_version": 1,
        "source": source,
        "status": _integrity_status(sum(error_counts.values()), sum(warning_counts.values())),
        "counts": {
            "conversations": len(payload),
            "messages": total_messages,
            "attachments": total_attachments,
            "file_references": total_files,
            "messages_with_attachments": messages_with_attachments,
            "messages_with_files": messages_with_files,
            "root_messages": sum(parent is None for _, _, _, parent in parent_records),
        },
        "identity": {
            "unique_conversation_uuids": len(conversation_ids),
            "unique_message_uuids": len(message_ids),
            "duplicate_conversation_uuids": duplicate_conversations,
            "duplicate_message_uuids": duplicate_messages,
            "missing_parent_references": missing_parents,
            "external_root_parent_references": external_root_parents,
            "orphaned_parent_references": orphaned_parent_references,
            "cross_conversation_parent_references": cross_conversation_parents,
            "self_parent_references": self_parents,
        },
        "timestamps": {
            "earliest": min(created_values).isoformat() if created_values else None,
            "latest": max(updated_values).isoformat() if updated_values else None,
        },
        "schema": {
            "conversation_fields": dict(sorted(conversation_fields.items())),
            "message_fields": dict(sorted(message_fields.items())),
            "unknown_conversation_fields": unknown_conversation_fields,
            "unknown_message_fields": unknown_message_fields,
            "content_types": dict(sorted(content_types.items())),
            "senders": dict(sorted(sender_counts.items())),
            "attachment_types": dict(sorted(attachment_types.items())),
        },
        "content_integrity": {
            "explicit_markers": dict(sorted(marker_counts.items())),
            "text_locations": dict(sorted(text_locations.items())),
            "unicode": unicode_stats.as_dict(),
        },
        "readiness": {
            "message_uuid_provenance_usable": (
                not duplicate_messages and not error_counts["message_missing_uuid"]
            ),
            "exact_thread_reconstruction_usable": (
                missing_parents == 0
                and cross_conversation_parents == 0
                and self_parents == 0
                and not error_counts["parent_cycles"]
            ),
            "explicit_truncation_detected": bool(marker_counts),
            "text_normalization_required": bool(
                unicode_stats.controls
                or unicode_stats.replacement_characters
                or unicode_stats.unpaired_surrogates
            ),
            "recommended_action": (
                "stop"
                if error_counts
                else "proceed_with_constraints"
                if warning_counts
                else "proceed"
            ),
        },
        "errors": [{"code": code, "count": count} for code, count in sorted(error_counts.items())],
        "warnings": [
            {"code": code, "count": count} for code, count in sorted(warning_counts.items())
        ],
        "privacy": {
            "contains_message_text": False,
            "contains_names": False,
            "contains_uuid_values": False,
            "contains_file_names": False,
        },
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    source = report["source"]
    lines = [
        "# Claude Export Integrity Report",
        "",
        f"Status: **{report['status']}**",
        "",
        "## Source",
        "",
        f"- File: `{source['file_name']}`",
        f"- Size: {source['size_bytes']} bytes",
        f"- SHA-256: `{source['sha256']}`",
    ]
    if "counts" not in report:
        lines.extend(
            [
                "",
                "## Failure",
                "",
                f"- Parse error category: `{report.get('parse_error', 'unknown')}`",
            ]
        )
        return "\n".join(lines) + "\n"

    counts = report["counts"]
    identity = report["identity"]
    timestamps = report["timestamps"]
    content = report["content_integrity"]
    unicode_data = content["unicode"]
    lines.extend(
        [
            "",
            "## Corpus",
            "",
            f"- Conversations: {counts['conversations']}",
            f"- Messages: {counts['messages']}",
            f"- Attachments: {counts['attachments']}",
            f"- File references: {counts['file_references']}",
            f"- Time range: `{timestamps['earliest']}` to `{timestamps['latest']}`",
            "",
            "## Identity And Parent Links",
            "",
            f"- Unique conversation UUIDs: {identity['unique_conversation_uuids']}",
            f"- Duplicate conversation UUIDs: {identity['duplicate_conversation_uuids']}",
            f"- Unique message UUIDs: {identity['unique_message_uuids']}",
            f"- Duplicate message UUIDs: {identity['duplicate_message_uuids']}",
            f"- Missing parent references: {identity['missing_parent_references']}",
            f"- External/root parent references: {identity['external_root_parent_references']}",
            f"- Orphaned non-root parent references: {identity['orphaned_parent_references']}",
            f"- Cross-conversation parent references: {identity['cross_conversation_parent_references']}",
            f"- Self-parent references: {identity['self_parent_references']}",
            "",
            "## Content Integrity",
            "",
            f"- Content block types: `{json.dumps(report['schema']['content_types'], sort_keys=True)}`",
            f"- Explicit truncation markers: `{json.dumps(content['explicit_markers'], sort_keys=True)}`",
            f"- Decoded text characters inspected: {unicode_data['characters']}",
            f"- Non-ASCII characters: {unicode_data['non_ascii']}",
            f"- Control characters excluding newline/tab: {unicode_data['controls_excluding_newline_tab']}",
            f"- Unicode replacement characters: {unicode_data['replacement_characters']}",
            f"- Unpaired Unicode surrogates: {unicode_data['unpaired_surrogates']}",
            "",
            "## Findings",
            "",
        ]
    )
    errors = report["errors"]
    warnings = report["warnings"]
    readiness = report["readiness"]
    lines.append(
        "- Errors: none" if not errors else f"- Errors: `{json.dumps(errors, sort_keys=True)}`"
    )
    lines.append(
        "- Warnings: none"
        if not warnings
        else f"- Warnings: `{json.dumps(warnings, sort_keys=True)}`"
    )
    lines.extend(
        [
            "",
            "## Extraction Readiness",
            "",
            f"- Recommended action: **{readiness['recommended_action']}**",
            f"- Message UUID provenance usable: {str(readiness['message_uuid_provenance_usable']).lower()}",
            f"- Exact thread reconstruction usable: {str(readiness['exact_thread_reconstruction_usable']).lower()}",
            f"- Explicit truncation detected: {str(readiness['explicit_truncation_detected']).lower()}",
            f"- Text normalization required: {str(readiness['text_normalization_required']).lower()}",
            "",
            "Unique message UUIDs can support source links. Missing parent nodes mean",
            "later extraction must not assume every conversation has a complete ancestry",
            "chain. The absence of explicit truncation markers does not prove that every",
            "upstream source was exported in full. Control and replacement characters",
            "must be normalized in a derived copy while preserving the raw export.",
            "",
            "## Privacy",
            "",
            "This report contains aggregate metadata only. It excludes conversation",
            "names, message text, UUID values, attachment names, and source excerpts.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit a Claude conversations export without emitting content."
    )
    parser.add_argument("export", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args(argv)

    report = audit_export(args.export)
    rendered = render_markdown(report)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(rendered, encoding="utf-8")
    if not args.json_output and not args.markdown_output:
        sys.stdout.write(rendered)
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())

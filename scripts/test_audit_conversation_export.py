from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("audit_conversation_export.py")
SPEC = importlib.util.spec_from_file_location("audit_conversation_export", SCRIPT_PATH)
assert SPEC is not None
audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


def _message(
    message_id: str,
    *,
    parent: str | None = None,
    text: str = "hello",
    content: list[dict] | None = None,
) -> dict:
    return {
        "uuid": message_id,
        "text": text,
        "content": content if content is not None else [{"type": "text", "text": text}],
        "sender": "human",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:01Z",
        "attachments": [],
        "files": [],
        "parent_message_uuid": parent,
    }


def _conversation(conversation_id: str, messages: list[dict]) -> dict:
    return {
        "uuid": conversation_id,
        "name": "private title",
        "summary": "private summary",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:02Z",
        "account": {"uuid": "account-private"},
        "chat_messages": messages,
    }


def _write_export(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_valid_export_passes_without_private_content(tmp_path: Path) -> None:
    source = _write_export(
        tmp_path / "conversations.json",
        [_conversation("c1", [_message("m1"), _message("m2", parent="m1", text="café")])],
    )

    report = audit.audit_export(source)
    rendered = json.dumps(report)

    assert report["status"] == "pass"
    assert report["counts"]["messages"] == 2
    assert report["identity"]["missing_parent_references"] == 0
    # Claude exports duplicate visible text in message.text and a text block.
    assert report["content_integrity"]["unicode"]["non_ascii"] == 2
    assert "private title" not in rendered
    assert "private summary" not in rendered
    assert "account-private" not in rendered
    assert "café" not in rendered


def test_duplicate_fails_and_missing_parent_warns(tmp_path: Path) -> None:
    source = _write_export(
        tmp_path / "conversations.json",
        [
            _conversation("c1", [_message("m1"), _message("m1", parent="missing")]),
        ],
    )

    report = audit.audit_export(source)
    error_codes = {item["code"] for item in report["errors"]}
    warning_codes = {item["code"] for item in report["warnings"]}

    assert report["status"] == "fail"
    assert report["identity"]["duplicate_message_uuids"] == 1
    assert report["identity"]["missing_parent_references"] == 1
    assert "duplicate_message_uuids" in error_codes
    assert "orphaned_parent_references" in warning_codes


def test_external_root_parent_is_reported_as_warning(tmp_path: Path) -> None:
    source = _write_export(
        tmp_path / "conversations.json",
        [_conversation("c1", [_message("m1", parent="external-root")])],
    )

    report = audit.audit_export(source)

    assert report["status"] == "pass_with_warnings"
    assert report["identity"]["external_root_parent_references"] == 1
    assert report["identity"]["orphaned_parent_references"] == 0


def test_truncation_and_unicode_controls_warn(tmp_path: Path) -> None:
    source = _write_export(
        tmp_path / "conversations.json",
        [
            _conversation(
                "c1",
                [
                    _message(
                        "m1",
                        text="visible\u0001",
                        content=[
                            {
                                "type": "tool_result",
                                "content": [{"type": "text", "text": "result"}],
                                "truncated": True,
                            }
                        ],
                    )
                ],
            )
        ],
    )

    report = audit.audit_export(source)
    warning_codes = {item["code"] for item in report["warnings"]}

    assert report["status"] == "pass_with_warnings"
    assert report["content_integrity"]["explicit_markers"]["truncated_true"] == 1
    assert "explicit_truncation_markers" in warning_codes
    assert "embedded_control_characters" in warning_codes


def test_invalid_json_fails_without_echoing_input(tmp_path: Path) -> None:
    source = tmp_path / "conversations.json"
    source.write_text('{"secret": "do not echo"', encoding="utf-8")

    report = audit.audit_export(source)
    rendered = audit.render_markdown(report)

    assert report["status"] == "fail"
    assert report["errors"] == [{"code": "unreadable_json", "count": 1}]
    assert "do not echo" not in rendered


def test_markdown_report_is_aggregate_only(tmp_path: Path) -> None:
    source = _write_export(
        tmp_path / "conversations.json",
        [_conversation("secret-conversation-id", [_message("secret-message-id")])],
    )

    rendered = audit.render_markdown(audit.audit_export(source))

    assert "secret-conversation-id" not in rendered
    assert "secret-message-id" not in rendered
    assert "private title" not in rendered
    assert "Messages: 1" in rendered

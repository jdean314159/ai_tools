from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).with_name("normalize_conversation_corpus.py")
SPEC = importlib.util.spec_from_file_location(
    "normalize_conversation_corpus",
    SCRIPT_PATH,
)
assert SPEC is not None
normalizer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = normalizer
SPEC.loader.exec_module(normalizer)


def _message(
    message_id: str,
    text: str,
    *,
    parent: str | None = None,
    attachments: list[dict] | None = None,
) -> dict:
    return {
        "uuid": message_id,
        "text": text,
        "content": [{"type": "text", "text": text}],
        "sender": "human",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:01Z",
        "attachments": attachments or [],
        "files": [],
        "parent_message_uuid": parent,
    }


def _conversation(index: int, messages: list[dict]) -> dict:
    return {
        "uuid": f"c{index}",
        "name": f"private title {index}",
        "summary": f"private summary {index}",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:02Z",
        "account": {"uuid": "private-account"},
        "chat_messages": messages,
    }


def _selection() -> dict:
    return {
        "selection_version": 1,
        "selection_policy": "test",
        "conversations": [
            {"conversation_uuid": f"c{index}", "reason": "test"}
            for index in range(10)
        ],
    }


def test_normalize_text_preserves_meaningful_unicode() -> None:
    raw = "\ufeffcafé\u00a0— ✅\r\nline\u0001  \n\n\n\nnext"

    text, operations = normalizer.normalize_text(raw)

    assert text == "café — ✅\nline\n\n\nnext"
    assert operations["crlf_to_lf"] == 1
    assert operations["nbsp_to_space"] == 1
    assert operations["control_characters_removed"] == 1
    assert operations["format_characters_removed"] == 1
    assert operations["trailing_whitespace_trimmed"] == 1
    assert operations["blank_line_runs_collapsed"] == 1


def test_observe_text_counts_preserved_unicode() -> None:
    observations = normalizer.observe_text("café \ue000 \ufffd \u200d")

    assert observations == {
        "format_characters_preserved": 1,
        "non_ascii_characters": 4,
        "private_use_characters": 1,
        "replacement_characters": 1,
    }


def test_iter_records_excludes_titles_names_and_content_blocks() -> None:
    conversation = _conversation(
        0,
        [
            _message(
                "m1",
                "assessment",
                attachments=[
                    {
                        "file_name": "private.txt",
                        "file_type": "txt",
                        "file_size": 4,
                        "extracted_content": "article",
                    }
                ],
            )
        ],
    )

    records = list(normalizer.iter_records(conversation))
    rendered = json.dumps(records)

    assert [record["source_kind"] for record in records] == [
        "message_text",
        "attachment_extracted_content",
    ]
    assert "private title" not in rendered
    assert "private summary" not in rendered
    assert "private.txt" not in rendered
    assert "private-account" not in rendered
    assert records[1]["source_metadata"] == {"file_type": "txt"}


def test_build_corpus_writes_deterministic_private_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversations = [
        _conversation(
            index,
            [_message(f"m{index}", f"article {index}", parent="external-root")],
        )
        for index in range(10)
    ]
    export_path = tmp_path / "conversations.json"
    selection_path = tmp_path / "selection.json"
    output_path = tmp_path / "corpus.jsonl"
    manifest_path = tmp_path / "manifest.json"
    export_path.write_text(json.dumps(conversations), encoding="utf-8")
    selection_path.write_text(json.dumps(_selection()), encoding="utf-8")
    monkeypatch.setattr(
        normalizer,
        "EXPECTED_EXPORT_SHA256",
        normalizer.sha256_file(export_path),
    )

    first = normalizer.build_corpus(
        export_path,
        selection_path,
        output_path,
        manifest_path,
    )
    first_bytes = output_path.read_bytes()
    second = normalizer.build_corpus(
        export_path,
        selection_path,
        output_path,
        manifest_path,
    )

    assert first == second
    assert output_path.read_bytes() == first_bytes
    assert first["conversation_count"] == 10
    assert first["record_count"] == 10
    assert first["parent_status_counts"] == {"external_root": 10}
    assert first["contains_private_text"] is False
    assert first["normalized_corpus_is_private"] is True


def test_build_corpus_rejects_wrong_export_hash(tmp_path: Path) -> None:
    export_path = tmp_path / "conversations.json"
    selection_path = tmp_path / "selection.json"
    export_path.write_text("[]", encoding="utf-8")
    selection_path.write_text(json.dumps(_selection()), encoding="utf-8")

    with pytest.raises(ValueError, match="Export hash differs"):
        normalizer.build_corpus(
            export_path,
            selection_path,
            tmp_path / "corpus.jsonl",
            tmp_path / "manifest.json",
        )


def test_selection_requires_exactly_ten_unique_uuids(tmp_path: Path) -> None:
    selection = _selection()
    selection["conversations"] = selection["conversations"][:9]
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(selection), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly ten"):
        normalizer.load_selection(path)

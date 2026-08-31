from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).with_name("extract_knowledge_candidates.py")
SPEC = importlib.util.spec_from_file_location(
    "extract_knowledge_candidates",
    SCRIPT_PATH,
)
assert SPEC is not None
extractor = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = extractor
SPEC.loader.exec_module(extractor)


def _record(
    index: int,
    text: str,
    *,
    conversation_uuid: str = "c1",
) -> dict:
    return {
        "conversation_uuid": conversation_uuid,
        "message_uuid": f"m{index}",
        "sender": "assistant",
        "source_kind": "message_text",
        "source_index": None,
        "raw_sha256": f"raw-{index}",
        "normalized_sha256": f"normalized-{index}",
        "normalized_text": text,
    }


def test_source_units_split_records_with_stable_ranges() -> None:
    records = [_record(1, "a" * (extractor.MAX_SOURCE_UNIT_CHARS + 5))]

    units = extractor.source_units(records)

    assert [unit["source_unit_id"] for unit in units] == [
        "r000001p001",
        "r000001p002",
    ]
    assert units[0]["char_start"] == 0
    assert units[0]["char_end"] == extractor.MAX_SOURCE_UNIT_CHARS
    assert units[1]["char_start"] == extractor.MAX_SOURCE_UNIT_CHARS
    assert units[1]["char_end"] == extractor.MAX_SOURCE_UNIT_CHARS + 5


def test_source_units_include_only_assistant_message_text() -> None:
    assistant = _record(1, "assistant")
    human = {**_record(2, "human"), "sender": "human"}
    attachment = {
        **_record(3, "attachment"),
        "source_kind": "attachment_extracted_content",
    }

    units = extractor.source_units([assistant, human, attachment])

    assert [unit["record_index"] for unit in units] == [1]


def test_batches_never_mix_conversations() -> None:
    units = extractor.source_units(
        [
            _record(1, "a" * 100, conversation_uuid="c1"),
            _record(2, "b" * 100, conversation_uuid="c2"),
        ]
    )

    batches = extractor.build_batches(units)

    assert len(batches) == 2
    assert batches[0]["conversation_uuid"] == "c1"
    assert batches[1]["conversation_uuid"] == "c2"


def test_validate_claims_rejects_unknown_source_reference() -> None:
    result = extractor.CandidateBatch(
        claims=[
            extractor.ProposedClaim(
                statement="Evaluation should use explicit tasks and failure criteria.",
                scope="LLM application evaluation",
                evidence_kind="secondary_assessment",
                source_refs=["unknown"],
            )
        ]
    )

    with pytest.raises(ValueError, match="outside its batch"):
        extractor.validate_claims(result, allowed_source_refs={"r000001p001"})


def test_validate_claims_normalizes_and_deduplicates() -> None:
    claim = extractor.ProposedClaim(
        statement="  Evaluation   should use explicit tasks and failure criteria. ",
        scope=" LLM application evaluation ",
        evidence_kind="secondary_assessment",
        qualifications=[" Use task-specific metrics. "],
        source_refs=["r000001p001", "r000001p001"],
    )

    validated = extractor.validate_claims(
        extractor.CandidateBatch(claims=[claim, claim]),
        allowed_source_refs={"r000001p001"},
    )

    assert len(validated) == 1
    assert validated[0].statement == ("Evaluation should use explicit tasks and failure criteria.")
    assert validated[0].source_refs == ["r000001p001"]


def test_candidate_id_is_deterministic() -> None:
    claim = extractor.ProposedClaim(
        statement="Evaluation should use explicit tasks and failure criteria.",
        scope="LLM application evaluation",
        evidence_kind="secondary_assessment",
        source_refs=["r000001p001"],
    )
    batch = {"batch_id": "b0001-test", "conversation_uuid": "c1"}

    assert extractor.candidate_record(claim, batch) == extractor.candidate_record(
        claim,
        batch,
    )


def test_prompt_names_exact_schema_fields() -> None:
    batch = {
        "units": [
            {
                "source_unit_id": "r000001p001",
                "source_kind": "message_text",
                "text": "assessment",
            }
        ]
    }

    prompt = extractor.render_batch_prompt(batch)

    assert '"statement"' in prompt
    assert '"scope"' in prompt
    assert '"evidence_kind"' in prompt
    assert '"source_refs"' in prompt


def test_load_corpus_verifies_hash_and_count(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    manifest = tmp_path / "manifest.json"
    corpus.write_text(json.dumps(_record(1, "text")) + "\n", encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "normalized_corpus_sha256": extractor.sha256_file(corpus),
                "record_count": 1,
            }
        ),
        encoding="utf-8",
    )

    records, loaded_manifest = extractor.load_corpus(corpus, manifest)

    assert len(records) == 1
    assert loaded_manifest["record_count"] == 1

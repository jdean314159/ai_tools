from __future__ import annotations

import json
from pathlib import Path

from llm_harness_core import (
    SyntheticDataConfig,
    generate_memory_records,
    generate_retrieval_documents,
    generate_synthetic_bundle,
    write_synthetic_bundle,
)


def test_generate_memory_records_counts_and_kinds() -> None:
    records = generate_memory_records("Project Atlas", count=12, preset="adversarial", seed=11)
    assert len(records) == 12
    kinds = {record.metadata.get("record_kind") for record in records}
    assert "canonical" in kinds
    assert "contradiction" in kinds
    assert "noise" in kinds


def test_generate_retrieval_documents_counts_and_kinds() -> None:
    docs = generate_retrieval_documents("Project Atlas", count=12, preset="noisy", seed=11)
    assert len(docs) == 12
    kinds = {doc.metadata.get("doc_kind") for doc in docs}
    assert "canonical" in kinds
    assert "contradiction" in kinds
    assert "noise" in kinds


def test_write_synthetic_bundle_outputs_manifest_and_jsonl(tmp_path: Path) -> None:
    bundle = generate_synthetic_bundle(
        SyntheticDataConfig(
            topic="Project Atlas", preset="clean", memory_count=6, retrieval_count=7, seed=5
        )
    )
    paths = write_synthetic_bundle(bundle, tmp_path)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["memory_count"] == 6
    assert manifest["retrieval_count"] == 7
    assert paths["memory_records"].read_text(encoding="utf-8").count("\n") == 6
    assert paths["retrieved_documents"].read_text(encoding="utf-8").count("\n") == 7

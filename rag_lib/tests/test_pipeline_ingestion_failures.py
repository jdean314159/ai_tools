from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from rag_lib.errors import RagLibError, StorageError
from rag_lib.ingestion.chunker import TextChunk
from rag_lib.ingestion.loader import LoadedDocument
from rag_lib.pipeline import RAGPipeline


def _pipeline(*, storage_failure: bool = False, bm25_failure: bool = False) -> RAGPipeline:
    pipeline = object.__new__(RAGPipeline)
    pipeline._loader = MagicMock()
    pipeline._loader.load.return_value = LoadedDocument(
        text="word " * 20,
        tables=[],
        source_path="/private/input.txt",
        doc_type="paper",
        file_hash="a" * 16,
        content_digest="a" * 64,
    )
    chunk = TextChunk(
        text="model visible text",
        context_text="model visible text",
        source_id="/private/input.txt:0",
        doc_type="paper",
        chunk_index=0,
    )
    pipeline._chunker = MagicMock()
    pipeline._chunker.chunk.return_value = [chunk]
    pipeline._table_processor = MagicMock()
    pipeline._table_processor.process.return_value = []
    pipeline._enricher = None
    pipeline._embedder = MagicMock()
    pipeline._embedder.embed.return_value = [[0.1, 0.2]]
    pipeline._store = MagicMock()
    pipeline._store.delete_by_source.return_value = 0
    if storage_failure:
        pipeline._store.add.side_effect = StorageError("fabricated storage failure")
    pipeline._retriever = MagicMock()
    pipeline._retriever._load_all_chunks_from_store.return_value = [MagicMock()]
    if bm25_failure:
        pipeline._retriever.build_bm25_index.side_effect = RuntimeError(
            "fabricated BM25 failure"
        )
    return pipeline


def test_storage_failure_is_returned_as_an_ingestion_error(tmp_path):
    pipeline = _pipeline(storage_failure=True)
    source = tmp_path / "input.txt"
    source.write_text("word " * 20)

    result = pipeline.ingest(source)

    assert result.chunks_stored == 0
    assert result.errors == ["Storage failed: fabricated storage failure"]
    assert result.success is False


def test_strict_ingestion_raises_on_storage_failure(tmp_path):
    pipeline = _pipeline(storage_failure=True)
    source = tmp_path / "input.txt"
    source.write_text("word " * 20)

    with pytest.raises(RagLibError, match="fabricated storage failure"):
        pipeline.ingest(source, strict=True)


def test_bm25_rebuild_failure_is_returned_as_an_ingestion_error(tmp_path):
    pipeline = _pipeline(bm25_failure=True)
    source = tmp_path / "input.txt"
    source.write_text("word " * 20)

    result = pipeline.ingest(source)

    assert result.chunks_stored == 1
    assert len(result.errors) == 1
    assert "fabricated BM25 failure" in result.errors[0]
    assert result.success is False


def test_sanitized_source_id_replaces_private_path_before_storage(tmp_path):
    pipeline = _pipeline()
    source = tmp_path / "input.txt"
    source.write_text("word " * 20)

    result = pipeline.ingest(source, source_id="corpus/document-1")

    stored_chunk = pipeline._store.add.call_args.args[0][0]
    assert result.source_path == "corpus/document-1"
    assert stored_chunk.source_id == "corpus/document-1:0"
    assert str(tmp_path) not in stored_chunk.source_id


@pytest.mark.parametrize("source_id", ["/absolute/path", "../escape", "a/../../escape"])
def test_source_id_rejects_absolute_and_parent_paths(tmp_path, source_id):
    pipeline = _pipeline()
    source = tmp_path / "input.txt"
    source.write_text("word " * 20)

    with pytest.raises(ValueError, match="source_id"):
        pipeline.ingest(source, source_id=source_id)

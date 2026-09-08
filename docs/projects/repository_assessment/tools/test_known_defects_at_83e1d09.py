"""Objective grader for the repository-assessment target at commit 83e1d09.

The tests are expected to fail 3/3 when the target packages are imported from
commit 83e1d09 and pass 3/3 when they are imported from the corrected checkout.
They are external to the model's assessment transcript and were written after
the target commit's defects had already existed and been independently fixed.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engram import ProjectMemory
from engram.concurrency import WriterLock
from rag_lib.retrieval.retriever import HybridRetriever
from rag_lib.storage.base import StoredChunk


class RecordingEmbedder:
    dimension = 2

    def __init__(self) -> None:
        self.single_calls: list[str] = []
        self.batch_calls: list[list[str]] = []

    def embed(self, text: str) -> SimpleNamespace:
        self.single_calls.append(text)
        return SimpleNamespace(embedding=[float(len(text)), 1.0])

    def embed_batch(self, texts: list[str]) -> SimpleNamespace:
        self.batch_calls.append(list(texts))
        return SimpleNamespace(embeddings=[[float(len(text)), 1.0] for text in texts])


class RecordingChroma:
    def __init__(self) -> None:
        self.added: list[tuple[str, str]] = []
        self.batch_calls = 0

    def add(self, *, episode_id: str, text: str, embedding, metadata) -> None:
        del embedding, metadata
        self.added.append((episode_id, text))

    def add_batch(self, **kwargs) -> None:
        del kwargs
        self.batch_calls += 1


def test_batch_storage_indexes_each_accepted_episode_once() -> None:
    embedder = RecordingEmbedder()
    chroma = RecordingChroma()
    memory = ProjectMemory(embedder=embedder, enable_embedding_cache=False)
    memory.chromadb = chroma

    stats = memory.store_episodes_batch(
        [
            {"text": "", "importance": 0.95},
            {"text": "Atlas uses blue deployment slots.", "importance": 0.95},
            {"text": "Planning occurs every Friday at noon.", "importance": 0.95},
        ]
    )

    assert stats == {"stored": 2, "indexed": 2}
    assert embedder.batch_calls == []
    assert chroma.batch_calls == 0


def test_dead_pid_text_does_not_replace_locked_inode(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    lock_path = project_dir / WriterLock.LOCK_FILE
    owner_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(owner_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.write(owner_fd, b"999999999\n")
    original_inode = lock_path.stat().st_ino

    contender = WriterLock(project_dir)
    try:
        with pytest.raises(RuntimeError, match="Writer lock held"):
            contender.acquire(timeout=0.01)
        assert lock_path.stat().st_ino == original_inode
    finally:
        contender.release()
        fcntl.flock(owner_fd, fcntl.LOCK_UN)
        os.close(owner_fd)


def _chunk(text: str, chunk_id: str) -> StoredChunk:
    return StoredChunk(
        chunk_id=chunk_id,
        text=text,
        context_text=text,
        score=0.5,
        source_id=f"doc:{chunk_id}",
        doc_type="paper",
        metadata={"strategy": "fixed_size"},
    )


def test_disk_bm25_cache_rebuilds_after_store_mutation(tmp_path: Path) -> None:
    pytest.importorskip("rank_bm25")
    new_chunk = _chunk("new content", "new")
    store = MagicMock()
    store.search.return_value = [new_chunk]
    store.count.return_value = 1
    store.collection_metadata.return_value = {"updated_at": 20.0}
    cache_dir = tmp_path / "bm25"
    cache_dir.mkdir()
    (cache_dir / "test.json").write_text(
        json.dumps({"corpus": ["old content"], "ids": ["old"], "built_at": 10.0}),
        encoding="utf-8",
    )
    retriever = HybridRetriever(
        store=store,
        embedder=MagicMock(),
        bm25_path=str(cache_dir),
    )

    _index, ids = retriever._get_bm25_index("test")

    assert ids == ["new"]
    assert store.search.called

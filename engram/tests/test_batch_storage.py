from __future__ import annotations

from types import SimpleNamespace

from engram import ProjectMemory


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
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.added: list[tuple[str, str]] = []
        self.batch_calls = 0

    def add(self, *, episode_id: str, text: str, embedding, metadata) -> None:
        if self.fail:
            raise RuntimeError("index unavailable")
        self.added.append((episode_id, text))

    def add_batch(self, **kwargs) -> None:
        del kwargs
        self.batch_calls += 1


def _memory_with_recorders(*, fail_index: bool = False):
    embedder = RecordingEmbedder()
    chroma = RecordingChroma(fail=fail_index)
    memory = ProjectMemory(embedder=embedder, enable_embedding_cache=False)
    memory.chromadb = chroma
    return memory, embedder, chroma


def test_batch_storage_indexes_each_accepted_episode_exactly_once() -> None:
    memory, embedder, chroma = _memory_with_recorders()
    episodes = [
        {"text": "", "importance": 0.95},
        {"text": "Atlas uses blue deployment slots.", "importance": 0.95},
        {"text": "Planning occurs every Friday at noon.", "importance": 0.95},
    ]

    stats = memory.store_episodes_batch(episodes)

    assert stats == {"stored": 2, "indexed": 2}
    assert embedder.single_calls == [episodes[1]["text"], episodes[2]["text"]]
    assert embedder.batch_calls == []
    assert [text for _episode_id, text in chroma.added] == [
        episodes[1]["text"],
        episodes[2]["text"],
    ]
    assert chroma.batch_calls == 0


def test_batch_storage_does_not_report_failed_indexing() -> None:
    memory, _embedder, _chroma = _memory_with_recorders(fail_index=True)

    stats = memory.store_episodes_batch(
        [{"text": "Remember the release checklist.", "importance": 0.95}]
    )

    assert stats == {"stored": 1, "indexed": 0}
    assert memory._episode_embeddings == {}

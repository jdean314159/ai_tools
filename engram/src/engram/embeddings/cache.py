from __future__ import annotations
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import List, Optional
from .base import Embedder, EmbeddingResult, BatchEmbeddingResult


class EmbeddingCache:
    """SQLite-backed embedding cache. Key: sha256(text::model)."""

    def __init__(self, cache_path: Path):
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.cache_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                cache_key TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                model TEXT NOT NULL,
                embedding TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_model ON embeddings(model)")
        conn.commit()
        conn.close()

    def _make_key(self, text: str, model: str) -> str:
        return hashlib.sha256(f"{text}::{model}".encode()).hexdigest()

    def get(self, text: str, model: str) -> Optional[List[float]]:
        key = self._make_key(text, model)
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.execute("SELECT embedding FROM embeddings WHERE cache_key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return json.loads(row[0]) if row else None

    def put(self, result: EmbeddingResult):
        key = self._make_key(result.text, result.model)
        conn = sqlite3.connect(self.cache_path)
        conn.execute(
            """INSERT OR REPLACE INTO embeddings
               (cache_key, text, model, embedding, dimension, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                key,
                result.text,
                result.model,
                json.dumps(result.embedding),
                result.dimension,
                time.time(),
            ),
        )
        conn.commit()
        conn.close()

    def get_stats(self) -> dict:
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.execute("SELECT COUNT(*), COUNT(DISTINCT model) FROM embeddings")
        total, models = cursor.fetchone()
        conn.close()
        return {"total_embeddings": total, "unique_models": models}


class CachedEmbedder:
    """Transparent caching wrapper around any Embedder."""

    def __init__(self, embedder: Embedder, cache: EmbeddingCache):
        self.embedder = embedder
        self.cache = cache
        self.hits = 0
        self.misses = 0

    @property
    def model_name(self) -> str:
        return self.embedder.model_name

    @property
    def dimension(self) -> int:
        return self.embedder.dimension

    def embed(self, text: str) -> EmbeddingResult:
        cached = self.cache.get(text, self.embedder.model_name)
        if cached is not None:
            self.hits += 1
            return EmbeddingResult(
                text=text,
                embedding=cached,
                model=self.embedder.model_name,
                dimension=len(cached),
            )
        self.misses += 1
        result = self.embedder.embed(text)
        self.cache.put(result)
        return result

    def embed_batch(self, texts: List[str]) -> BatchEmbeddingResult:
        results = [None] * len(texts)
        uncached_indices = []
        uncached_texts = []

        for i, text in enumerate(texts):
            cached = self.cache.get(text, self.embedder.model_name)
            if cached is not None:
                self.hits += 1
                results[i] = cached
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if uncached_texts:
            self.misses += len(uncached_texts)
            batch = self.embedder.embed_batch(uncached_texts)
            for local_i, global_i in enumerate(uncached_indices):
                embedding = batch.embeddings[local_i]
                results[global_i] = embedding
                self.cache.put(
                    EmbeddingResult(
                        text=batch.texts[local_i],
                        embedding=embedding,
                        model=self.embedder.model_name,
                        dimension=self.dimension,
                    )
                )

        return BatchEmbeddingResult(
            texts=texts,
            embeddings=results,
            model=self.embedder.model_name,
            dimension=self.dimension,
        )

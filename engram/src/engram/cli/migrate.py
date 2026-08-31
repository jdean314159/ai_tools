"""Migration tool: upgrade engram v1.0 projects to v2.0."""

from __future__ import annotations
import argparse
import json
import sys
import uuid
import time
from pathlib import Path


def migrate_embeddings(project_dir: Path, embedder_model: str, batch_size: int = 50) -> int:
    from engram.embeddings.ollama import OllamaEmbedder
    from engram.embeddings.cache import EmbeddingCache, CachedEmbedder
    from engram.storage.chromadb_store import ChromaDBStore

    episodes_file = project_dir / "episodes.jsonl"
    if not episodes_file.exists():
        print("No episodes.jsonl found")
        return 0

    episodes = []
    with episodes_file.open() as f:
        for line in f:
            if line.strip():
                episodes.append(json.loads(line))
    print(f"  Found {len(episodes)} episodes")

    embedder = CachedEmbedder(
        OllamaEmbedder(model=embedder_model),
        EmbeddingCache(project_dir / "embedding_cache.db"),
    )
    chromadb = ChromaDBStore(
        persist_directory=project_dir / "episodic",
        collection_name=f"{project_dir.name}_episodes",
        embedding_dimension=embedder.dimension,
    )
    chromadb.rebuild_from_episodes(episodes, embedder, batch_size=batch_size)
    print(
        f"  Indexed: {chromadb.count()} | Cache hits: {embedder.hits} | misses: {embedder.misses}"
    )
    return chromadb.count()


def migrate_paired_exchanges(project_dir: Path) -> int:
    sessions_dir = project_dir / "sessions"
    if not sessions_dir.exists():
        print("  No sessions directory, skipping pairing")
        return 0

    episodes_file = project_dir / "episodes.jsonl"
    added = 0

    for session_file in sessions_dir.glob("*.jsonl"):
        session_id = session_file.stem
        turns = []
        with session_file.open() as f:
            for line in f:
                if line.strip():
                    turns.append(json.loads(line))

        for i in range(len(turns) - 1):
            if (
                str(turns[i].get("role", "")).lower() == "user"
                and str(turns[i + 1].get("role", "")).lower() == "assistant"
            ):
                user_text = turns[i].get("text", "")
                asst_text = turns[i + 1].get("text", "")
                episode = {
                    "id": f"migrated_pair_{uuid.uuid4().hex[:8]}",
                    "text": f"User: {user_text}\nAssistant: {asst_text}",
                    "importance": 0.6,
                    "created_at": time.time(),
                    "metadata": {
                        "type": "exchange",
                        "session_id": session_id,
                        "user_text": user_text,
                        "assistant_text": asst_text,
                        "migrated": True,
                    },
                }
                with episodes_file.open("a") as f:
                    f.write(json.dumps(episode) + "\n")
                added += 1

    print(f"  Paired exchanges added: {added}")
    return added


def migrate_semantic_graph(project_dir: Path, llm_engine=None) -> int:
    from engram.semantic.extractor import SemanticExtractor
    from engram.semantic.graph import SemanticGraph

    episodes_file = project_dir / "episodes.jsonl"
    if not episodes_file.exists():
        return 0

    episodes = []
    with episodes_file.open() as f:
        for line in f:
            if line.strip():
                episodes.append(json.loads(line))

    graph = SemanticGraph(persist_path=project_dir / "semantic_graph.json")
    extractor = SemanticExtractor(llm_engine=llm_engine, pattern_only=(llm_engine is None))

    extracted = 0
    for ep in episodes:
        text = ep.get("text", "")
        if not text:
            continue
        result = extractor.extract(text, role="user")
        for fact in result.facts:
            fact_id = f"fact:{uuid.uuid4().hex[:8]}"
            graph.add_fact(
                fact_id=fact_id,
                fact_type=fact.fact_type,
                subject=fact.subject,
                value=fact.value,
                confidence=fact.confidence,
                source_episode_id=ep.get("id"),
            )
            extracted += 1

    graph.save()
    print(f"  Facts extracted: {extracted}")
    return extracted


def main():
    parser = argparse.ArgumentParser(description="Migrate engram project to v2.0")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--embedder-model", default="nomic-embed-text")
    parser.add_argument("--skip-embeddings", action="store_true")
    parser.add_argument("--skip-pairing", action="store_true")
    parser.add_argument("--skip-semantic", action="store_true")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    if not args.project_dir.exists():
        print(f"Error: {args.project_dir} does not exist")
        sys.exit(1)

    print(f"Migrating: {args.project_dir}")
    print("=" * 50)

    if not args.skip_embeddings:
        print("\nPhase 1: Backfilling embeddings...")
        migrate_embeddings(args.project_dir, args.embedder_model, args.batch_size)

    if not args.skip_pairing:
        print("\nPhase 2: Building paired exchanges...")
        migrate_paired_exchanges(args.project_dir)

    if not args.skip_semantic:
        print("\nPhase 3: Extracting semantic facts...")
        migrate_semantic_graph(args.project_dir)

    from engram.storage.schema import SchemaManager
    from engram.version import SCHEMA_VERSION

    SchemaManager(args.project_dir).set_version(SCHEMA_VERSION)
    print(f"\nMigration complete! Schema: {SCHEMA_VERSION}")


if __name__ == "__main__":
    main()

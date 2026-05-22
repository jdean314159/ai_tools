"""CLI: reconcile ChromaDB against JSONL source of truth."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def reconcile_project(project_dir: Path, embedder_model: str, dry_run: bool = False):
    from engram.embeddings.ollama import OllamaEmbedder
    from engram.embeddings.cache import EmbeddingCache, CachedEmbedder
    from engram.storage.chromadb_store import ChromaDBStore

    print(f"Reconciling: {project_dir}")
    episodes_file = project_dir / "episodes.jsonl"
    if not episodes_file.exists():
        print("No episodes.jsonl found")
        return

    episodes = []
    with episodes_file.open() as f:
        for line in f:
            if line.strip():
                ep = json.loads(line)
                if ep.get("id"):
                    episodes.append(ep)

    jsonl_ids = {ep["id"] for ep in episodes}
    print(f"JSONL episodes: {len(jsonl_ids)}")

    embedder = CachedEmbedder(
        OllamaEmbedder(model=embedder_model),
        EmbeddingCache(project_dir / "embedding_cache.db"),
    )
    chroma_dir = project_dir / "episodic"
    if not chroma_dir.exists():
        print("No ChromaDB directory. Run migrate first.")
        return

    chromadb = ChromaDBStore(
        persist_directory=chroma_dir,
        collection_name=f"{project_dir.name}_episodes",
        embedding_dimension=embedder.dimension,
    )
    chroma_data = chromadb.collection.get()
    chroma_ids = set(chroma_data["ids"])
    print(f"ChromaDB episodes: {len(chroma_ids)}")

    missing = jsonl_ids - chroma_ids
    orphaned = chroma_ids - jsonl_ids
    print(f"Missing in ChromaDB: {len(missing)} | Orphaned: {len(orphaned)}")

    if dry_run:
        print("\n[Dry run] No changes made")
        return

    added = 0
    for ep in episodes:
        if ep["id"] not in missing:
            continue
        try:
            emb = embedder.embed(ep.get("text", "")).embedding
            chromadb.add(episode_id=ep["id"], text=ep.get("text", ""),
                         embedding=emb, metadata=ep.get("metadata", {}))
            added += 1
        except Exception as e:
            print(f"Failed to add {ep['id']}: {e}")

    removed = 0
    for oid in orphaned:
        try:
            chromadb.delete(oid)
            removed += 1
        except Exception:
            pass

    print(f"\nDone. Added: {added} | Removed: {removed}")


def main():
    parser = argparse.ArgumentParser(description="Reconcile ChromaDB against JSONL")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--embedder-model", default="nomic-embed-text")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.project_dir.exists():
        print(f"Error: {args.project_dir} does not exist")
        sys.exit(1)

    reconcile_project(args.project_dir, args.embedder_model, args.dry_run)


if __name__ == "__main__":
    main()

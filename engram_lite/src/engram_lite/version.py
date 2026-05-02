__version__ = "0.2.0"
SCHEMA_VERSION = "2.0"

SCHEMA_MIGRATIONS = {
    "1.0": {
        "description": "Original engram_lite (text-only, no pairing)",
        "features": ["jsonl_storage", "text_scoring", "session_history"],
    },
    "2.0": {
        "description": "Restored engram_lite (vector search, pairing, semantic)",
        "features": [
            "jsonl_storage",
            "text_scoring",
            "session_history",
            "chromadb_vector_search",
            "embedding_cache",
            "assistant_pairing",
            "semantic_graph",
            "fact_extraction",
            "contradiction_detection",
            "forgetting_policy",
        ],
    },
}

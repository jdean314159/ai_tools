from __future__ import annotations

CORPUS = {
    "engine": "An engine layer normalizes backend differences and response metadata.",
    "memory": "Memory augmentation should be inspectable and justified.",
    "rag": "Retrieval systems should show what was retrieved, reranked, and dropped.",
}


def retrieve(query: str) -> list[str]:
    terms = query.lower().split()
    return [text for key, text in CORPUS.items() if any(term in key or term in text.lower() for term in terms)]


def main() -> int:
    query = "Why should retrieval be inspectable?"
    hits = retrieve(query)
    print("Source-grounded QA starter")
    print(f"Query: {query}")
    print("Retrieved snippets:")
    for hit in hits:
        print(f"- {hit}")
    print("Next step: replace toy retrieval with rag_lib and emit an inspectable retrieval trace.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

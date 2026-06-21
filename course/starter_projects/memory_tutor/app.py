from __future__ import annotations


def select_memories(memories: list[str], query: str) -> list[str]:
    return [memory for memory in memories if query.lower() in memory.lower()]


def main() -> int:
    memories = [
        "Learner prefers concise explanations.",
        "Learner is currently studying retrieval augmentation.",
    ]
    query = "retrieval"
    selected = select_memories(memories, query)
    print("Memory tutor starter")
    print(f"Selected memories for query {query!r}: {selected}")
    print("Next step: replace this toy selector with an engram retrieval path.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

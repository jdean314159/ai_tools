# Assistant Turn Pairing

`engram_lite` automatically pairs assistant responses with their preceding user turns to store complete conversational exchanges.

## How It Works

When `auto_pair_assistant=True` (default):

1. User turn added → stored to episodic memory (existing behavior)
2. Assistant turn added → checks for preceding user turn in same session
3. If found → creates paired text: `"User: {user}\nAssistant: {assistant}"`
4. Stores paired exchange to episodic memory

This matches full `engram` behavior and improves retrieval quality: instead of isolated messages, you get complete Q&A pairs.

## Configuration

```python
memory = ProjectMemory(
    auto_pair_assistant=True,  # Enable pairing (default)
    paired_exchange_importance=0.6,  # Importance for exchanges
    orphan_assistant_handling="skip",  # How to handle orphans
)
```

### Orphan Handling

An "orphan" is an assistant turn with no preceding user turn. Options:

- `"skip"` (default): Don't store to episodic memory
- `"store"`: Store unpaired (at 50% of normal importance)
- `"warn"`: Log warning and skip

## Retrieving Exchanges

```python
# Standard search returns paired text
results = memory.search_episodes(query="Python programming", n=5)
for r in results:
    print(r.text)  # "User: What is Python?\nAssistant: Python is..."

# Structured retrieval
exchanges = memory.get_paired_exchanges(query="Python", n=5)
for ex in exchanges:
    print(f"Q: {ex['user']}")
    print(f"A: {ex['assistant']}")
```

## Disabling Pairing

For use cases where you only want user context:

```python
memory = ProjectMemory(auto_pair_assistant=False)
```

User turns are still auto-stored; assistant turns go to session history only.

## Migration

Existing projects without pairing can continue working. To rebuild with pairing:

1. Enable `auto_pair_assistant=True`
2. New turns will be paired going forward
3. Old episodes remain unpaired (manual rebuild not required)
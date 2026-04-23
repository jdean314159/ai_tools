# Synthetic data generator for memory and retrieval labs

Use the shared synthetic data generator to create small corpora for memory and RAG exercises.

Example:

```bash
PYTHONPATH=llm_harness_core/src:. python scripts/generate_synthetic_data.py \
  --topic "Project Atlas" \
  --preset adversarial \
  --memory-count 18 \
  --retrieval-count 18 \
  --output-dir artifacts/synthetic_atlas
```

This writes:
- `memory_records.jsonl`
- `retrieved_documents.jsonl`
- `manifest.json`

Presets:
- `clean` — mostly canonical records with a small amount of noise
- `noisy` — more noise and distractors
- `adversarial` — more contradictions and misleading historical notes

Use cases:
- stress-testing memory contamination handling
- creating broken-RAG distractor corpora
- quick classroom demos without hand-writing dozens of examples

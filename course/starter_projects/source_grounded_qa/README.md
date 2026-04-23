# Source-grounded QA starter

This starter introduces a retrieval-backed question answering shape.

Suggested exercises:
1. Replace the toy retrieval function with `rag_lib` retrieval.
2. Add reranking and filtering.
3. Show which sources were included in the final prompt.
4. Extend `eval.py` so it compares baseline vs grounded answers on your own questions.
5. Add a separate evidence-presence check so correctness and grounding are scored independently.

Default command:

```bash
python course/starter_projects/source_grounded_qa/eval.py
```

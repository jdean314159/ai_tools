# Broken RAG lab

This lab demonstrates a common retrieval failure mode: a retriever selects text that is semantically or lexically similar to the query, but not relevant to the user's task.

In the demo, a query about **Project Mercury deployment region** initially retrieves an astronomy note about the planet Mercury. The repaired pipeline adds a lightweight topic guardrail so the project operations note is selected first.

## Run the example

```bash
PYTHONPATH=rag_lib/src:llm_inspector/src:llm_harness_core/src:llm_engines:. python rag_lib/examples/broken_rag_lab.py
```

## What to inspect

- the selected chunks for the broken and repaired pipelines
- the `Evidence flow:` section in the inspector output
- provenance fields, especially `source`, `doc_id`, `topic`, and `guardrail`
- the evaluation summary showing the repaired pipeline passes and the broken one fails

## Teaching goal

Students should learn that retrieval quality is not just about similarity. They should inspect the evidence flow, identify why the wrong chunk was chosen, apply a relevance guardrail or reranking fix, and then re-evaluate the result.

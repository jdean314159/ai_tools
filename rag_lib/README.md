# rag_lib

## Tier: beta

## Scope

Retrieval-augmented generation pipeline. Ingests documents, indexes them, and
retrieves relevant chunks to augment LLM prompts. Chunkers, rerankers, and
embedders are implementation details — the public API is `RAGPipeline`.
Does not run inference.

## Quick start

```python
from rag_lib import RAGPipeline

pipeline = RAGPipeline()                    # uses default config
pipeline.ingest_directory("./docs")         # index a directory
results = pipeline.retrieve("What is RAG?") # retrieve relevant chunks
prompt = pipeline.assemble_prompt("What is RAG?", results)
print(prompt)
```

`RAGPipeline.ingest()` ingests one file; use `ingest_directory()` for a tree.
`assemble_prompt()` requires the chunks returned by `retrieve()`.

The `evaluate()` API and ground-truth loader reserve the intended RAGAS
integration surface, but external-judge execution is not implemented yet and
currently raises `NotImplementedError`. Use the deterministic evaluation labs
under `rag_lib.eval` for current offline comparisons; do not build production
evaluation code on `RAGPipeline.evaluate()` yet.



`rag_lib` is the retrieval package for the `ai_tools` suite.

Its job is not only to retrieve context for LLMs, but also to make retrieval behavior inspectable so users can understand what the retriever did and why.

## Using this with the rest of the suite

- pair it with `llm_inspector` or `llm_inspector_ui`
- compare baseline vs grounded runs using the evaluation walkthrough

## Current support status

This package is the **default** retrieval path and is **active and recommended**.

## Responsibilities

- chunk/document retrieval
- ranking and reranking
- evidence selection
- prompt assembly from retrieved context
- retrieval-stage tracing and diagnostics
- conversion to shared interop objects

## Position in the stack

Typical composition:

```text
llm_engines + rag_lib + llm_inspector + llm_inspector_ui
```

## Observability expectations

`rag_lib` should not behave as a black box.

Important things it should make visible include:

- what documents/chunks were retrieved
- scores, ranks, and reranking effects
- what was kept vs dropped
- what context was finally assembled for the model
- warnings, thresholds, or degraded behavior when applicable

## Interop

`rag_lib` participates in the shared `llm_harness_core` vocabulary.

That includes:

- shared retrieved documents
- shared operation results
- shared trace events for retrieval stages
- retrieval-oriented capability/inspection helpers

## UI role

`llm_inspector_ui` is intended to expose `rag_lib` behavior directly so users can inspect retrieval quality rather than simply trusting it.

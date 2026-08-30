# Engram clean-wheel packaging validation — 2026-08-30

## Outcome

Wheels built successfully for `llm-harness-core` 0.1.0 and Engram 0.2.0 after
installing the declared `wheel` build requirement into the repository-local
development environment.

Two fresh Python 3.13 virtual environments installed only from the generated
project wheels plus resolved third-party dependencies:

- Base Engram: wheel-origin import, temporal set/update, current filtering,
  historical retrieval, prompt provenance, and shared stage attribution passed.
- `engram[sentence-transformers]`: wheel-origin import, cached MiniLM loading on
  CPU, 384-dimensional embeddings, Chroma persistence, cold reopen, vector use,
  current filtering, and historical retrieval passed.

The first base dependency install was blocked by sandbox DNS and succeeded when
repeated with network authorization. This was an environment restriction, not
a package failure.

## Findings

- The copied repository `.venv` had `build` but lacked `wheel`; `wheel` 0.48.0
  was installed to perform the build.
- The Sentence Transformers extra resolved a large PyTorch/CUDA dependency set
  on Linux despite CPU execution. The README now marks this extra as
  heavyweight and recommends planning disk/cache cost or using Ollama
  embeddings when appropriate.
- Sentence Transformers 6.0 renamed its dimension method. Engram now prefers
  `get_embedding_dimension()` and falls back for older releases.

Temporary wheels and validation environments were created under `/tmp`; they
are not repository artifacts.

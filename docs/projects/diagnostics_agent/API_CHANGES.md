# Diagnostics Agent API Changes

## 2026-05-31

- Added `llm_engines.resolve_ollama_gguf_path(model, models_dir=None)` and
  `OllamaModelResolutionError` so applications can resolve an Ollama-managed model
  tag to its local GGUF blob for llama.cpp reuse without re-downloading the model.

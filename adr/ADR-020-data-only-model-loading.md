# ADR-020 — Data-Only Model & Artifact Loading

**Status:** Accepted (documents an existing invariant + one enforcement commit; no new subsystem).
**Date:** 2026-06.
**Context:** Model-supply-chain concern — can an untrusted model (any origin) compromise the
system or its data? This ADR records the controls `ai_tools` *already* relies on, makes them a
stated invariant rather than an accident, and names the verification points. It deliberately does
**not** add origin allowlists, weight scanning, or signature infrastructure — no concrete exposure
forces them, and building them would be speculative per the campaign build rule.

---

## Decision

`ai_tools` treats model weights and cached artifacts as **data, never as code**. Concretely, the
following are invariants, enforced and verifiable today:

1. **No in-process weight deserialization.** `ai_tools` does not load model weights into its own
   Python process. Model access is HTTP to a local inference server (llama.cpp / Ollama / vLLM);
   `llm_engines/discovery.py` resolves Ollama models to local GGUF blobs over raw urllib with no
   `ollama` package dependency. The weights are deserialized by the inference engine (a separately
   built, trusted binary — llama.cpp compiled from source), not by `ai_tools`. The process boundary,
   not just the file format, is the control.

2. **GGUF / safetensors only; no pickle-format model checkpoints.** Where model artifacts are
   referenced, they are GGUF (llama.cpp) or safetensors — data-only formats with no code-execution
   path on load. The legacy PyTorch pickle checkpoint formats (`.bin`/`.pt`/`.ckpt`) are not loaded
   anywhere in `ai_tools`.

3. **No `trust_remote_code`.** Active Python paths contain no `trust_remote_code=True`
   (verified by grep). Model repos' bundled Python is never executed as part of model loading.

4. **No pickle in data caches.** As of the BM25 cache fix (see Enforcement), no active Python source
   or test path calls `pickle.load`/`pickle.dump`. Caches that previously used pickle now serialize
   as JSON and rebuild live objects from data on load. This removes the arbitrary-code-execution
   surface that a pickle cache exposes if its path is ever attacker-writable — relevant as
   multi-agent file access grows (an `agent_lib` worker writing a cache later read by another
   component is a privilege crossing pickle would turn into code execution).

## Why this is the right scope (and what is out of scope)

The supply-chain concern has three distinct layers, and they need different responses:

- **System/data compromise via loading** (weights or bundled code executing on load) — addressed by
  invariants 1–4 above. This is the layer where a control is justified, and it is largely already in
  place by construction of the local-first GGUF/HTTP design. Origin-independent: the same controls
  protect against a malicious checkpoint from any source.
- **Poisoned/backdoored model behavior** (weights trained to emit insecure code or triggered output)
  — not addressable by load-time controls, because the weights are data and behave as trained. The
  mitigation is the existing two-tool review loop (specs read, generated code reviewed) and not
  acting on model output unverified. No code control added here; it is a process control already in
  use.
- **Provenance / policy** (what models are *permitted* on an air-gapped DoD system) — an
  institutional control, not a code control. `ai_tools` does not encode an origin policy; that
  belongs to the deploying environment. This ADR records the technical posture such a policy would
  rely on, nothing more.

**Explicitly out of scope** (no forcing exposure; would be speculative over-building): model-origin
allowlists/denylists, in-repo weight scanning, checkpoint signature verification, and any
"trusted-vendor" gating. If a concrete exposure later forces one of these (e.g., a workflow that
must load a third-party pickle checkpoint), that is a new ADR with its own forcing case.

## Enforcement

- **Commit (BM25 cache):** `5692881` (`fix(rag_lib): replace pickle BM25 cache with JSON`)
  converts the `rag_lib` BM25 cache from pickle to data-only JSON with live rebuild of
  `BM25Okapi` on load; removes the dead `import pickle` from `storage/chroma.py`; and reaps
  both `.json` and legacy `.pkl` caches on collection deletion. Verified:
  `rg "import pickle|pickle\.(load|dump)" rag_lib/src rag_lib/tests` → no matches; 94 passed /
  4 skipped.
- **Standing checks (cheap, greppable):**
  - `rg "trust_remote_code" --glob '*.py' .` → expected empty.
  - `rg "pickle\.(load|dump)|torch\.load" --glob '*.py' .` → expected empty.
  - New model backends must access weights via the inference-server boundary, not in-process
    deserialization. A backend that loads weights into the `ai_tools` process is a deviation
    requiring its own review.

## Verification still open (not blocking this ADR)

Agentic-execution boundary: confirm no `agent_lib` tool path executes model-proposed code outside a
sandbox. Expected outcome is "no gap" given COORD-01 never-execute routing and narrow per-agent tool
grants (ADR-017), but it has not been audited end-to-end. Recorded here as a follow-on check, not a
control this ADR claims to have completed.

# agent_coordination_teaching — API Changes & Refinement Record

Records public API changes and refinements made while adopting Codex's
lightweight ASC draft as `examples/agent_coordination_teaching`.

## Required public API change: `get_engine("llamacpp", ...)` was broken

The example's `LLMEngineWorkerAdapter` wants to construct a llama.cpp engine
via the public `get_engine`. That path was broken in
`llm_engines/factory.py`:

- The generic block set `kwargs["model"] = model`, but `LlamaCppEngine.__init__`
  takes `model_path`, not `model`. Any call would `TypeError` on construction.
- The llama.cpp branch tried to pass `base_url` and `gguf_path` to
  `LlamaCppEngine`, neither of which it accepts.
- `n_ctx`, `n_threads`, `verbose`, and `embedding` were silently dropped.

Codex's original draft worked around this by reaching into
`llm_engines.backends.llamacpp` directly (a private import) — surfacing the
real defect.

**Fix applied** in `llm_engines/factory.py`:

- Translate the generic `model` arg to `model_path` for llama.cpp.
- Accept `gguf_path` as a config-file alias for the same thing.
- Drop `base_url` silently (it does not apply to in-process llama.cpp).
- Pass through `n_gpu_layers`, `n_ctx`, `n_threads` (int-coerced) and
  `verbose`, `embedding` (bool-coerced).

After the fix, `get_engine("llamacpp", "/path/model.gguf", n_gpu_layers=40,
n_ctx=8192)` works and the example uses it via the public surface.

This is the only public API change required. Everything else uses existing
public symbols.

## Refinements applied during adoption

1. **Private import removed.** `LLMEngineWorkerAdapter` now constructs the
   engine via `get_engine("llamacpp", ...)`. No reach into
   `llm_engines.backends.*`.

2. **Structured output via the public handler.** The planner's hand-rolled
   `json.loads` + try/except parsing was replaced with
   `StructuredOutputHandler.parse_with_details` against Pydantic schemas
   (`_PlanModel` / `_AssignmentModel`). Instructions are generated from the
   schema via `create_schema_prompt`. This is the second example to hit this
   pattern (after the language tutor); a public `generate_and_parse` helper
   is justified once a third consumer hits the same shape.

3. **In-process worker made text-only.** The `LLMEngineWorkerAdapter` no
   longer writes a response file into the workspace. It has no isolation
   boundary, so per ADR-011 it returns text only — the exchange log persists
   it, but the workspace is not modified. For real coding-agent work, prefer
   the Codex or Claude Code adapters under container-isolated runners.

4. **Isolation status documented honestly.** The README and inline comments
   in `workers.py` now state what is and isn't sandboxed, pointing to
   ADR-011 and `AGENT_BUILD_NOTES.md` §4 for the recommended baseline.

5. **Public-API audit test added.** `test_only_public_ai_tools_imports`
   statically parses every `.py` file in the example and asserts no dotted
   ai_tools imports (the rule that fails on `llm_engines.backends.llamacpp`).
   The original Codex draft's tests would not have caught the private import;
   this one does.

6. **README is now explicit about scope.** It states what this is (an
   `agent_lib` coordination teaching example) and what it isn't (the
   worker/mentor ASC from `AGENT_BUILD_NOTES.md` §4). That decision follows
   the co-evolution rule in §0.

## Verification status

Import-level acceptance check passes (static audit run; no private imports
in any example source file). Runtime tests must be run locally — the build
sandbox lacks `pydantic` and network access.

    pytest examples/agent_coordination_teaching/test_demo.py
    python -m examples.agent_coordination_teaching.run_demo --workers mock

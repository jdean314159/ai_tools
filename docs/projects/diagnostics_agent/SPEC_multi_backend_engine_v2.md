# Build Spec — Multi-Backend Engine Selection + Failover + Structured-Output Swap

**Project:** `examples/diagnostics_agent`; one new helper in `llm_engines`.
**Type:** glue + one justified `llm_engines` addition + one parsing swap.
**Why:** The diagnostics agent hardcodes `OllamaEngine` in two UI sites and discovers
only via Ollama. The laptop (4 GB GTX 1650) needs llama.cpp CPU-offload or
workstation-over-LAN fallback, and weak laptop models produce messier JSON than the
current bespoke parser handles well. This spec routes engine construction through the
public `get_engine`, lets llama.cpp/vLLM reuse Ollama-managed GGUFs, adds robust
failover with a local-only guarantee, and swaps the interpreter's hand-rolled JSON
parse for the library's repair-capable handler.

Four parts. Each is independently testable; land in order.

---

## Part A — `llm_engines` addition: resolve an Ollama model name to its GGUF path

**This is a justified library change** (co-evolution: diagnostics is the first
consumer needing it). Record it in the campaign API_CHANGES.

**Where:** `llm_engines/llm_engines/discovery.py` (next to the other Ollama helpers),
exported from the package `__init__` `__all__`.

**Why net-new:** `list_ollama_models` returns only a 12-char digest *prefix*
(`model_id`), not a usable path. Ollama stores GGUFs as content-addressed blobs
(`<store>/blobs/sha256-<digest>`) with a manifest (`<store>/manifests/.../<model>/<tag>`)
mapping name+tag to layer digests. Resolving name → GGUF path requires reading that
on-disk layout; no existing helper does it.

**Function:**

```python
def resolve_ollama_gguf_path(
    model: str,
    *,
    models_dir: str | Path | None = None,
) -> Path:
    """Resolve an Ollama model name[:tag] to the on-disk GGUF blob path.

    models_dir defaults to $OLLAMA_MODELS or ~/.ollama/models.
    Raises OllamaModelResolutionError if the manifest is missing, the tag is
    absent, the model has no single GGUF layer, or the blob file does not exist.
    """
```

**Implementation notes:**
- Default `models_dir`: `$OLLAMA_MODELS` if set, else `~/.ollama/models`.
- Manifest path: `models_dir/manifests/registry.ollama.ai/library/<name>/<tag>`
  (tag defaults to `latest` when `model` has none). Models may live under a
  namespace other than `library/` (custom/registry models) — search the manifests
  tree for a matching `<name>/<tag>` rather than hardcoding `library`. If multiple
  match, raise and list them; do not guess.
- Parse the manifest JSON; find the layer whose `mediaType` contains
  `model` / is the GGUF model layer (Ollama uses
  `application/vnd.ollama.image.model`). Take its `digest`
  (`sha256:<hex>`), map to `models_dir/blobs/sha256-<hex>` (note the `:` → `-`
  in the filename).
- **Fail loud, never guess.** Raise a new `OllamaModelResolutionError`
  (subclass of a discovery error or `ValueError`) with an actionable message if:
  manifest dir/file absent, tag not found, no single model layer (e.g. sharded or
  non-GGUF), or the resolved blob path does not exist on disk. The caller (UI)
  surfaces this verbatim.
- **Layout is an Ollama implementation detail**, not a documented API. Add a module
  comment saying so, and make the error message name the path it looked for, so a
  future Ollama layout change produces a clear diagnostic instead of a wrong path.

**Tests** (`llm_engines` test suite): build a fake `models_dir` tmptree with a
manifest JSON pointing at a fake blob file; assert correct resolution; assert each
failure mode raises with a message naming the missing piece. No real Ollama needed.

---

## Part B — Engine construction helper — new `engine_select.py` (diagnostics)

Both UI sites must build engines identically; centralize so they cannot drift.

```python
@dataclass(frozen=True)
class EngineChoice:
    backend: str                     # "ollama" | "llamacpp" | "vllm"
    model: str                       # ollama tag | gguf path | vllm served name
    base_url: str | None = None      # ollama LAN / vllm endpoint
    n_gpu_layers: int | None = None  # llamacpp
    n_ctx: int | None = None         # llamacpp
    fallback: "EngineChoice | None" = None  # optional secondary (Part C)

def build_single_engine(choice: EngineChoice):
    """One ChatModel via the public get_engine factory. No backend imports."""
    if choice.backend == "ollama":
        kw = {"base_url": choice.base_url} if choice.base_url else {}
        return get_engine("ollama", choice.model, **kw)
    if choice.backend == "llamacpp":
        kw = {}
        if choice.n_gpu_layers is not None: kw["n_gpu_layers"] = choice.n_gpu_layers
        if choice.n_ctx is not None: kw["n_ctx"] = choice.n_ctx
        return get_engine("llamacpp", choice.model, **kw)  # model = GGUF path
    if choice.backend == "vllm":
        kw = {"base_url": choice.base_url} if choice.base_url else {}
        return get_engine("vllm", choice.model, **kw)
    raise ValueError(f"unsupported backend: {choice.backend}")
```

Use the public `get_engine` only — no `from llm_engines.backends...`. If
`get_engine("llamacpp", path, n_gpu_layers=...)` does not forward the kwarg to
`LlamaCppEngine`, that is a second justified `llm_engines` gap — fix the factory
passthrough, record in API_CHANGES; do not import the backend.

---

## Part C — Failover wrapper with enforced local-only — `engine_select.py`

The laptop's robust story is primary + fallback, not a lone engine. Wrap in
`FailoverEngine` with a policy that guarantees logs never leave the box.

```python
from llm_engines import FailoverEngine, FailoverPolicy

DIAGNOSTICS_POLICY = FailoverPolicy(
    allow_cloud_failover=False,   # security tool: never route logs to cloud
    reduce_output_on_oom=True,    # directly helps the 4 GB card
    # cloud_policy left at default; irrelevant while allow_cloud_failover=False
)

def build_engine(choice: EngineChoice):
    engines = [build_single_engine(choice)]
    if choice.fallback is not None:
        engines.append(build_single_engine(choice.fallback))
    if len(engines) == 1:
        return engines[0]
    return FailoverEngine(engines, policy=DIAGNOSTICS_POLICY)
```

Rationale, verified against `router.py`:
- `FailoverEngine([...])` accepts a priority-ordered list; `generate` tries healthy
  engines in order with circuit-breaking.
- `allow_cloud_failover=False` + `_healthy_engines` skips any engine with
  `is_cloud=True`. ollama/llamacpp/vllm are not cloud (`_is_cloud` reads
  `getattr(engine,"is_cloud",False)`), so all three are eligible; a cloud engine
  could never be reached even if someone added one. This is the library-enforced
  version of the "stay local" posture the status doc calls for — stronger than the
  name-based guard alone.
- `reduce_output_on_oom=True` shrinks `max_tokens` (down to `min_max_tokens=256`)
  before abandoning an engine — the laptop-OOM mitigation, free.

The existing `require_local_engine` guard still runs in `LogInterpreter`/`FollowupChat`
per-member; confirm a `FailoverEngine` passes the guard. The guard inspects backend
id — if it does not recognize the wrapper, either (a) pass the guard the member
engines before wrapping, or (b) teach the guard to recurse into `FailoverEngine.engines`.
Prefer (a): guard each `build_single_engine` result at construction, then wrap. Keep
the guard's contract simple.

---

## Part D — UI wiring — `ui/app.py`

Add a **backend selector** above the model input; branch inputs by backend.

- **ollama:** existing auto-discovery dropdown (fit-annotated) + optional `base_url`
  text input (default `http://localhost:11434`), caption: "Point at another
  machine's Ollama over the LAN; treated as local/trusted." (This is the laptop →
  workstation path.)
- **llamacpp:** model source is a radio: **"Use an Ollama-managed model"** vs
  **"Custom GGUF path"**.
  - *Ollama-managed:* reuse the ollama discovery list for selection, then call
    `resolve_ollama_gguf_path(selected_name)` (Part A) to get the path; that path
    becomes `EngineChoice.model`. Surface a resolution error verbatim in `st.error`
    and disable Run. This is the "select from Ollama models, no re-download" feature
    requested.
  - *Custom path:* text input for a GGUF path.
  - Plus `n_gpu_layers` number input (default 0 = all CPU; caption "raise to offload
    layers onto a small GPU") and optional `n_ctx`.
- **vllm:** served model **name** + **endpoint** (`base_url`) text inputs only. **No
  Ollama list** — vLLM serves HF/safetensors models via an HTTP endpoint and does not
  consume Ollama GGUF blobs; offering the Ollama list here would mislead. (Caption
  may note this briefly.)

**Optional fallback control (Part C surfaced):** a checkbox "Fall back to another
Ollama (e.g. workstation) on failure" that reveals a second `base_url`; build a
`fallback=EngineChoice("ollama", <same model or chosen>, base_url=<lan>)`. Keep
minimal — a single optional Ollama fallback covers the main laptop case. Do not build
a full N-engine editor.

Replace BOTH hardcoded `OllamaEngine(model=...)` sites (interpret run + follow-up)
with `build_engine(choice)`. **Persist the run's `EngineChoice` in
`st.session_state`** so follow-up reuses the exact engine the interpretation used,
not rebuilt-from-current-widgets.

Fit annotation: keep for ollama. For llamacpp/vllm, show detected VRAM as a caption
(`detect_available_vram_bytes`) to inform `n_gpu_layers`, but do not block.

---

## Part E — Structured-output swap — `interpret.py`

Replace the bespoke parse + `_append_correction` retry loop with the library handler,
which extracts JSON from prose/markdown-fenced output (`_extract_json`) and repairs —
exactly the failure mode weak laptop models hit.

- Import `StructuredOutputHandler`, `StructuredOutputError` from `llm_engines`.
- In `interpret`, replace
  `Interpretation.model_validate_json(response.text)` with
  `StructuredOutputHandler.parse(response.text, Interpretation, allow_repair=True)`.
- Keep the two-attempt loop, but on first failure use `parse_with_details` to get the
  `error`/`extracted_json` and feed that into the existing `_append_correction`
  message (richer than the current generic correction). On final failure, raise
  `InterpretationParseError` from the `StructuredOutputError` (preserve the existing
  exception type the orchestrator catches — do not leak `StructuredOutputError` past
  the interpreter boundary).
- `_apply_operational_floor` and `_apply_risk_coherence` run unchanged on the parsed
  object.

Do **not** change the schema or the prompt. This is a parsing-robustness swap only.

---

## Non-goals

- No `ToolExecutor`, `recommend_role_placement`, or model lifecycle (pull/start) —
  out of diagnostics scope.
- No auto-suggested `n_gpu_layers` (resources advisory returns vLLM-style params, not
  a layer count) — manual knob stays.
- No N-engine failover editor — one optional fallback only.
- No vLLM-from-Ollama selection — technically inapplicable.

## Acceptance

- `make test-diagnostics` green; `llm_engines` resolver tests green.
  (Current diagnostics baseline 132 passed, 1 skipped; expect +~12 across Parts A/B/C/E.)
- `grep -n "backends" examples/diagnostics_agent/src/diagnostics_agent/ui/app.py`
  → empty (no direct backend imports).
- Backend selector offers ollama/llamacpp/vllm; llamacpp offers Ollama-managed vs
  custom GGUF and exposes `n_gpu_layers`; vllm takes served-name+endpoint only.
- `resolve_ollama_gguf_path` resolves a known model and raises clearly on each failure
  mode.
- A `FailoverEngine`-wrapped choice passes `require_local_engine`; cloud engines are
  structurally unreachable (`allow_cloud_failover=False`).
- Interpreter uses `StructuredOutputHandler`; still raises `InterpretationParseError`
  on unrecoverable output; floor + coherence unchanged.
- API_CHANGES records the resolver (and any factory kwarg-passthrough fix).

## Real-hardware validation (laptop, after merge — the point of the item)

1. **llama.cpp from Ollama model:** select an Ollama-pulled 7B Q4, low `n_gpu_layers`
   (~8–12, tune down on OOM), confirm it loads from the resolved blob (no
   re-download) and produces a grounded interpretation. Expect slow.
2. **Ollama-over-LAN fallback:** primary llama.cpp local, fallback Ollama →
   workstation IP; force the local to fail (or OOM) and confirm failover reaches the
   workstation, guard allows it, logs stay local.
3. **Structured-output:** confirm the swap reduces parse-failure retries vs the old
   parser on the weak model that previously produced messy JSON.
4. Record usable paths + numbers in the campaign doc; answers the status doc's open
   "is partial-offload on 4 GB worth it" with real data.

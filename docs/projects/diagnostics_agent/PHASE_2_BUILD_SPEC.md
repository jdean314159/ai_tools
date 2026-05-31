# Phase 2 Build Spec — LLM Interpretation (structured, local-only)

**For:** an autonomous coding agent (Codex).
**Parent:** `docs/projects/diagnostics_agent/CAMPAIGN.md`, Phase 2.
**Status:** committed.
**Spans two packages.** Do **Task A first** (it's a prerequisite), then Task B.

The interpreter consumes a Phase 1 `TriageSummary` and returns a **schema-enforced**
structured interpretation from a **local** model. No sandbox, no log reading, no
network beyond the local model endpoint. The sandbox→triage→interpret orchestrator
is a separate follow-on (see §C) and is **not** in this spec.

---

## Task A — `llm_engines`: wire `json_schema` through the local backends

### Context
`GenerationRequest.json_schema: dict | None` already exists. The `llamacpp` and
`ollama` backends ignore it and report `structured_output=False`. Wire it through
so the backend's native constrained decoding enforces the schema — malformed JSON
becomes structurally impossible, not retried.

### A1. llama.cpp backend (`backends/llamacpp.py`)
When `request.json_schema is not None`, include llama-server's documented
constrained-output field in the request payload the backend already sends:
`response_format = {"type": "json_schema", "schema": request.json_schema}`
(match the endpoint/payload shape the backend currently targets; llama-server
supports `response_format` with `json_schema`/`json_object`). Flip the capability
to `structured_output=True`.

### A2. Ollama backend (`backends/ollama.py`)
When `request.json_schema is not None`, set `payload["format"] = request.json_schema`
in `_base_payload`/`generate` (Ollama's `format` accepts a full JSON schema, not
just the string `"json"`). Flip the capability to `structured_output=True` and
remove the `# Phase 2` annotation.

### A3. Tests
- llamacpp: a `GenerationRequest` with `json_schema` set produces a payload
  containing the `response_format`/schema; without it, the payload is unchanged
  (no regression). Capability reports `structured_output=True`.
- ollama: `json_schema` set → `payload["format"]` equals the schema; unset →
  `format` absent. Capability `True`.
- Use the existing backend test patterns (mock HTTP / payload inspection); do not
  require a live server. Existing `llm_engines` tests must still pass.

### A4. Non-goals (Task A)
Do not touch vllm/anthropic/openai capability flags or payloads. Do not change the
`GenerationRequest` contract. Do not add dependencies.

---

## Task B — `diagnostics_agent`: the interpreter component

### B1. Deliverables (added to the existing package)
```
src/diagnostics_agent/
  interpret.py     # Interpretation model, LogInterpreter, typed errors
tests/
  test_interpret.py
```
New runtime deps for the package: `llm_engines` and (transitively) `pydantic`.
Record them in `pyproject.toml`.

### B2. Output schema (Pydantic) — field order is generation order under constrained decoding
```python
class ConcernAssessment(BaseModel):
    finding_ref: str                  # rule_name or cluster template this maps to
    severity: Literal["info", "low", "medium", "high", "critical"]
    rationale: str

class Interpretation(BaseModel):
    reasoning: str                    # FIRST — model reasons in prose before typed fields
    summary: str                      # one-line plain-language headline
    overall_risk: Literal["none", "low", "medium", "high", "critical"]
    prioritized_concerns: list[ConcernAssessment]
    recommended_checks: list[str]     # read-only next checks; advisory only this phase
```
`reasoning` is deliberately first: under grammar-constrained decoding the model
emits fields in schema order, so letting it "think" before committing typed values
mitigates the quality cost of forced formatting.

### B3. Interpreter
```python
class LogInterpreter:
    def __init__(self, engine, *, allow_remote: bool = False,
                 temperature: float = 0.2, max_tokens: int = 1024) -> None: ...
    def interpret(self, summary: TriageSummary) -> Interpretation: ...
```
- `engine` is any object implementing the `llm_engines` engine contract
  (`generate(GenerationRequest) -> GenerationResponse`). Inject it; do not construct
  a concrete backend inside the interpreter.
- **Local-only guard.** On construction, if the engine's backend identifier is a
  known remote backend (`{"openai", "anthropic"}`) and `allow_remote` is False,
  raise `RemoteEngineRefused`. Real log content (IPs, usernames, auth failures)
  must not leave the host. Document this; do not silently allow it.
- `interpret()` builds a `GenerationRequest` with:
  - a system message stating the role: read-only local diagnostics interpreter for
    a security-conscious operator; interpret only what is provided; do **not**
    invent events not present in the summary; correlate and prioritize by real risk.
  - a user message containing the serialized `summary.to_dict()` **and** an explicit
    prose description of each output field (the schema is *not* shown to the model —
    constrained decoding does not inject it — so the field meanings must be in the
    prompt).
  - `json_schema = Interpretation.model_json_schema()`, low `temperature`, `max_tokens`.
- Parse the response content into `Interpretation`. With a schema-enforcing local
  backend this should always parse; still wrap parsing and raise
  `InterpretationParseError` on failure (covers a non-enforcing engine). The
  existing `llm_engines` `StructuredOutputHandler` may be used for parse/validate.

### B4. Errors (`add to errors.py`)
`RemoteEngineRefused(SandboxError)`? No — interpretation is a separate concern;
create `class InterpreterError(Exception)` base with `RemoteEngineRefused` and
`InterpretationParseError` subclasses. Keep them distinct from the sandbox errors.

### B5. Tests (`test_interpret.py`, no network, no model)
Inject a **stub engine** (a small fake implementing `generate`, or the existing
`mock` backend) that returns a fixed `GenerationResponse` whose content is valid
`Interpretation` JSON.
- **Request construction:** the built `GenerationRequest` has `json_schema ==
  Interpretation.model_json_schema()`, a low temperature, and a user message whose
  text contains the findings/clusters from the summary (assert a known template or
  rule_name appears). This is the auditable prompt — assert it's stable.
- **Parse path:** stub returns valid JSON → `interpret()` returns a populated
  `Interpretation`; fields surface correctly.
- **Local-only guard:** a stub whose backend id is `"openai"` raises
  `RemoteEngineRefused`; with `allow_remote=True` it is permitted.
- **Parse failure:** stub returns malformed JSON → `InterpretationParseError`.
- **Determinism of prompt:** same `TriageSummary` → identical request messages
  (no `now()`, stable serialization), so the audit record is reproducible.
- **Schema field order:** assert `list(Interpretation.model_fields)` begins with
  `reasoning` (guards the constrained-decoding ordering rationale).

### B6. Non-goals (Task B)
No sandbox import, no log reading, no subprocess, no journalctl. No orchestrator
(see §C). No retry-on-semantic-quality loops. No cloud engine on the default path.
No streaming. Interpreter takes a `TriageSummary` already in hand.

---

## §C — Deferred to a separate follow-on (NOT this spec)

The end-to-end orchestrator that chains sandbox (`journalctl -o short-iso` /
file reads) → triage → interpret is the first place the Phase 0 §7 `/var/log`
permission wrinkle goes live and the first place a real model runs. Quarantine it
into one clearly-marked integration module with skip-guarded tests
(`skipif` no podman / no reachable model). Keep Phase 2's interpreter pure and
stub-testable so that messy seam stays isolated.

## Acceptance criteria
1. Task A: local backends forward `json_schema`; `structured_output=True` for both;
   existing `llm_engines` suite green.
2. Task B: interpreter unit tests pass with no model and no network (stub engine).
3. Local-only guard enforced by default; `allow_remote` is the only override.
4. `Interpretation` field order is `reasoning`-first and asserted.
5. Lint/type checks clean against the repo config for both packages.

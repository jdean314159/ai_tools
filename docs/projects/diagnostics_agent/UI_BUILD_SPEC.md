# UI Build Spec — Streamlit Front End

**For:** an autonomous coding agent (Codex).
**Parent:** `docs/projects/diagnostics_agent/CAMPAIGN.md`.
**Status:** committed (presentation layer; adds no new capability).
**Consumes:** `DiagnosticsOrchestrator` and the existing components. **Adds no
logic of its own** — it gathers config, builds the orchestrator, calls `run()`,
renders the result.

Two tasks: **Task A** (testable library helpers, no Streamlit) then **Task B**
(the thin app). Streamlit is an **optional extra**, never a core dependency.

---

## Task A — library helpers (no Streamlit, fully unit-testable)

### A1. Model discovery + VRAM-fit (`src/diagnostics_agent/models.py`)
```python
@dataclass(frozen=True)
class LocalModel:
    name: str                 # e.g. "qwen3:27b"
    size_bytes: int           # on-disk size reported by Ollama
    fit: str                  # "fits" | "tight" | "unlikely" | "unknown"

def estimate_fit(size_bytes: int, available_vram_bytes: int | None) -> str:
    """PURE. Compare size_bytes * overhead (use 1.2) to available VRAM.
    >= need -> 'fits'; within ~15% -> 'tight'; below -> 'unlikely';
    available None -> 'unknown'."""

def detect_available_vram_bytes() -> int | None:
    """Best-effort via llm_engines discovery (nvidia-smi path). None if no GPU
    or detection fails. Never raises."""

def list_local_models(
    *, ollama_host: str = "http://localhost:11434",
    available_vram_bytes: int | None = None,
) -> list[LocalModel]:
    """Query Ollama GET /api/tags, parse name + size, annotate each with
    estimate_fit(). Local models only — never returns cloud backends. Raises a
    typed error (or returns []) on connection failure; the caller surfaces it."""
```
Keep this in `diagnostics_agent` (thin) rather than expanding `llm_engines` scope;
promote later if a second consumer appears.

### A2. Collection-config factory (`src/diagnostics_agent/collect.py`, extend)
```python
_ALLOWED_PRIORITIES = ("emergency", "alert", "critical", "error", "warning")

def journalctl_collector(*, priority: str = "warning", since: str = "-24h") -> CommandCollector:
    """Build a CommandCollector for:
    journalctl -o json -p <priority> --since <since> --no-pager
    Validate priority against _ALLOWED_PRIORITIES; validate `since` against a
    strict pattern (e.g. -\\d+[hd] or ISO date). Build argv as a list — NEVER a
    shell string. Raise ValueError on invalid input. -o json is mandatory (correct
    PRIORITY-based severity)."""
```

### A3. Staged-read sandbox factory (`src/diagnostics_agent/sandbox.py`, add)
```python
def make_staging_sandbox(*, image: str = "docker.io/library/alpine:3.20") -> ReadOnlySandbox:
    """Sandbox configured to read host-user-owned 0600 staged files:
    user=f'{os.getuid()}:{os.getgid()}', extra_run_args=('--userns=keep-id',),
    plus the Phase 0 hardening defaults. This is the documented §C permission
    resolution — the UI and CLI both build their sandbox through here so the
    keep-id requirement is not tribal knowledge."""
```

### A4. Task A tests
- `estimate_fit`: parametrized fits/tight/unlikely/unknown against sample sizes.
- `list_local_models`: mock the Ollama `/api/tags` HTTP response → assert parsed
  names/sizes and that `fit` is populated; mock a connection failure → typed
  error/empty as specified. No live Ollama.
- `journalctl_collector`: asserts the exact argv for given priority/since; rejects
  an out-of-allowlist priority and a malformed `since`; never emits a shell string.
- `make_staging_sandbox`: asserts the config carries the current uid:gid and
  `--userns=keep-id`.

---

## Task B — the Streamlit app (`src/diagnostics_agent/ui/app.py`)

A thin view. All real work is Task A helpers + the orchestrator.

### B1. Controls (top of page)
- **Model picker:** `st.selectbox` populated from `list_local_models(...)`, each
  label annotated with its fit (e.g. `qwen3:8b  (fits)`, `qwen3:27b  (unlikely)`).
  Local models only. If Ollama is unreachable, show the error and disable Run.
- **Priority:** `st.selectbox` over `_ALLOWED_PRIORITIES`, default `warning`.
- **Time window:** `st.selectbox` mapping friendly labels to `since` values
  (Last 1h→`-1h`, 6h→`-6h`, 24h→`-24h`, 3 days→`-3d`), default 24h.
- **Run button:** `st.button("Run diagnostics")`.

### B2. Run handling (the long-run / rerun discipline)
Streamlit reruns the whole script on every interaction, and a run takes ~60s, so:
- Execute the orchestrator **only when the Run button returns True** on that
  rerun. Build: `journalctl_collector(...)` → `OllamaEngine(model=selected)` →
  `LogInterpreter(engine)` → `make_staging_sandbox()` → `DiagnosticsOrchestrator`.
- Wrap the call in `with st.spinner("Running diagnostics…")`.
- Store the `DiagnosticResult` (or the caught error) in `st.session_state`.
- **Render from `st.session_state`**, never by re-invoking `run()`. Changing the
  model dropdown or expanding the audit must not re-fire inference.

### B3. Rendering (from the stored result)
- **Run metadata:** collection command, bytes collected, sandbox read status
  (exit code / timed_out / truncated), timestamps.
- **Severity counts:** the `summary.severity_counts` as metrics or a small bar.
- **Findings:** if any, risk-ordered (rule_name, category, severity, count, examples).
- **Top clusters:** count, severity, template, a couple of examples.
- **Interpretation:** `overall_risk` prominent; `summary`; `prioritized_concerns`;
  `recommended_checks` as a list.
- **Raw audit:** an expander with the `audit` dict and a download button (JSON).
- **Partial result:** if `interpretation is None`, render the summary normally plus
  a clear notice showing `interpretation_error` — the triage is still useful.

### B4. Error surfaces (clear, actionable)
- `CollectionReadError` → show the message including the keep-id guidance.
- Collection command failure (not in `systemd-journal` group, journalctl absent)
  → surface the underlying error with the hint to add the user to
  `systemd-journal` and **not** to run the app as root.
- Ollama unreachable → shown at the model picker; Run disabled.

### B5. Packaging & run
- Optional extra in `pyproject.toml`: `[project.optional-dependencies] ui = ["streamlit"]`.
  Core library stays Streamlit-free.
- Document the launch line in the README: `streamlit run src/diagnostics_agent/ui/app.py`
  (or a console entry point), run as a `systemd-journal` group member, never root.

### B6. Tests
The view layer holds no testable logic (it all lives in Task A). The reasonable
bar: a smoke import test that the `app` module imports without launching the
server (guard any top-level execution behind `if __name__ == "__main__"` / a
`main()` so import is side-effect-free). Do not build Streamlit interaction tests.

---

## Non-goals
No cloud models (auth-log content stays local — the picker offers local backends
only). No writes/remediation. No multi-user, auth, or network exposure (single-user
local app — bind localhost). No scheduling or run-history persistence. No
LLM-generated queries (Phase 3). The UI adds presentation and control only; it must
not introduce any path that bypasses the orchestrator's guards.

## Acceptance criteria
1. Task A helpers pass unit tests with no live Ollama, no GPU, no container runtime.
2. `journalctl_collector` builds argv lists only and rejects invalid priority/since.
3. `make_staging_sandbox` encodes the keep-id + uid resolution; the UI builds its
   sandbox through it (no hardcoded podman flags in the app).
4. Running the app: changing a control does not re-execute inference; only the Run
   button does; results render from `session_state`.
5. Partial results (interpretation failed) render the summary plus the error.
6. Streamlit is an optional extra; importing the core library does not require it.
7. Lint/type checks clean against the repo config.
```

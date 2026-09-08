## Accepted Findings

### 1. `load_message_bodies` keys result dict by raw original Message-ID instead of normalized form

- **Scope:** `mail_lib`
- **File:** `mail_lib/thunderbird.py` — `load_message_bodies`
- **Severity:** High

**Claim:** `load_message_bodies` builds its result dict keyed by the original, un-normalized `header_message_id` (`found[original] = _message_body(message)`) instead of the normalized `target`, making the returned keys inconsistent with `load_message_body` (which normalizes via `normalize_message_id`) and with the rest of the package's Message-ID handling.

**Evidence:**
- `normalize_message_id` (line 85) strips surrounding whitespace and angle brackets.
- `load_message_body` (lines 299–307) computes `target = normalize_message_id(header_message_id)` and matches messages by `normalize_message_id(message.get("Message-ID")) == target` — i.e., keyed/looked-up by normalized value.
- `load_message_bodies` (line 314+) computes the same `target = normalize_message_id(header_message_id)` per input but stores `found[original] = _message_body(message)` keyed by the original un-normalized value. The single-input function normalizes while the batch function does not.

**Impact:** Callers that look up message bodies by normalized Message-ID using the dict returned by `load_message_bodies` will raise `KeyError` when the stored header Message-ID differs from its normalized form (e.g., differing angle brackets or surrounding whitespace), because the dict is keyed by the raw original value rather than the normalized key used everywhere else.

**Remediation:** Change `load_message_bodies` to key the result dict by the normalized target (`found[target] = _message_body(message)`) so returned keys match `load_message_body` and the package's normalized Message-ID convention.

---

## Rejected / Insufficient Candidates

### `assess_trajectory` truncation_point uses filtered enumerate offset instead of original trajectory index

- **Scope:** `action_trajectory_loop_guard`
- **Critic decision:** `insufficient_evidence`

The critic accepted that `assess_trajectory` builds a filtered action list via `enumerate`, that `_extract_action` defaults `sequence_offset` to the filtered enumerate offset, and that `loop_start_action` is derived from the 1-based original index. It also correctly noted these two indexing schemes coincide only when no non-tool events are filtered out.

However, the critic found the claim **not demonstrated** because the evidence failed to establish:
1. That `_extract_action` is ever called with a non-int `captured_offset` in a way that would make `sequence_offset` diverge from the original position, or that the enumerated offset is used at all when events are filtered;
2. How the caller actually uses `truncation_point` against `agent_steps` — whether `agent_steps` is the filtered list or the original trajectory, which determines whether any divergence is even observable; and
3. That the divergence produces the claimed corruption rather than being benign.

The disconfirmation_attempt itself conceded the mismatch is "latent" and only manifests when filtered and unfiltered positions differ, and no demonstration was provided that this divergence actually arises or corrupts behavior. The claim rests on a naming-scheme inconsistency without showing it is reachable or harmful.

---

## Coverage

The assessment covered **8 scopes** (per the coverage record). All scopes are marked `covered: true` except `agent_lib` (marked `covered: false`, with no corroborating reads).

| Scope | Covered | Production reads | Corroborating reads |
|---|---|---|---|
| `action_trajectory_loop_guard` | ✅ | `__init__.py`, `detector.py` | `README.md`, `tests/test_detector.py` |
| `agent_lib` | ❌ | `src/agent_lib/*.py`, `__init__.py`, `eval/*.py` | *(none)* |
| `engram` | ✅ | `src/engram/__init__.py` | `README.md` |
| `llm_engines` | ✅ | `src/llm_engines/__init__.py` | `README.md`, `pyproject.toml` |
| `llm_harness_core` | ✅ | `src/llm_harness_core/__init__.py`, `run_artifacts.py` | `README.md` |
| `llm_inspector` | ✅ | `src/llm_inspector/__init__.py` | `pyproject.toml` |
| `llm_inspector_ui` | ✅ | `src/llm_inspector_ui/__init__.py`, `interop.py` | `README.md`, `pyproject.toml` |
| `mail_lib` | ✅ | `__init__.py`, `thunderbird.py` | `README.md` |
| `rag_lib` | ✅ | `src/rag_lib/__init__.py` | `README.md` |

---

## Remaining Uncertainty

- **Controller uncertainty: medium.**
- The single accepted finding is confined to an internal-keying inconsistency within `mail_lib`; no findings were accepted in the other 8 scopes.
- `agent_lib` was not covered (no corroborating reads), so no determination was made there.
- The `action_trajectory_loop_guard` candidate, while logically plausible, was not accepted because the records contain no demonstration that the latent divergence is actually reachable or harmful in practice.

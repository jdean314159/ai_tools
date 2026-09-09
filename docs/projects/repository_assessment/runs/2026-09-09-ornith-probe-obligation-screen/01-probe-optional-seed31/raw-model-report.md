# Repository Assessment: `ai_tools`

## Executive Verdict

The repository is a modular, local-first Python suite of LLM harness/observability libraries. The **core library code is healthy**: 1,229 tests pass across all packages, and the passing suites exercise real behavior (characterization, memory, RAG, inspector, agent runtime).

I found **no validated correctness/security/data-integrity defects in the shipped library code.** The 21 failing tests are a single class of environmental failure: they assert SHA-256 digests of **committed run-artifact JSON files under `docs/projects/**/runs/` that are absent from this repo copy** (the `docs/projects/` tree is empty). These are pinned-byte regression tests whose fixture data was not included in the delivered tree. This is a repo-state/CI-data problem, not a defect in the library implementation.

I also confirmed a **separate, real defect**: `scripts/check_publication_hygiene.py` fails because it relies on `git ls-files` in a tree that is not a git repository (no `.git`), so it cannot verify fixture tracking. That is an environment/tooling issue rather than a library defect.

## Validated Findings

### F1 (Medium) — Pinned-byte regression tests fail because committed run-artifact fixtures are missing from the repo
- **Where:** `tests/test_engram_temporal_ab_probe.py::test_committed_temporal_ab_artifact_is_pinned_and_private` (line 53); `tests/test_engram_memory_security_probe.py`, `tests/test_engram_memory_security_policy_probe.py`, `tests/test_engram_dense_temporal_probe.py`, `tests/test_engram_longitudinal_update_probe.py`, `tests/test_engram_procedural_components_probe.py`, `tests/test_engram_procedural_transfer_probe.py`, `tests/test_engram_trust_availability_probe.py`, `tests/test_engram_trust_prompt_pressure_probe.py`, `tests/test_llm_context_retention_probe.py`, `tests/test_memory_inspection_probe.py`, `tests/test_vector_memory_probe.py`, `tests/test_agent_command_isolation_probe.py`, `tests/test_agent_policy_observability_probe.py`; `llm_engines/tests/test_characterization.py::test_committed_spark_artifacts_match_documented_bytes_and_privacy_boundary` (line 205); `llm_engines/tests/test_tool_recovery_probe.py::test_committed_recovery_artifacts_match_pinned_bytes_and_privacy` (line 289); `llm_inspector_ui/tests/test_artifact_replay.py::test_replay_supported_committed_artifact_without_execution` (line 14) and `::test_replay_unsupported_profile_is_envelope_only` (line 25); `scripts/test_compare_adjudication_strategies.py::test_few_shot_examples_are_unrelated_to_neural_case`; `scripts/test_validate_decision_history.py::test_adr_016_proof_case_passes`.
- **Impact:** 21 tests fail with `FileNotFoundError` on paths like `docs/projects/runs/2026-08-30-spark-qwen-engram-temporal-ab-v1.json`, `docs/projects/llm_engines/runs/...`, `docs/projects/agent_lib/runs/...`, `docs/projects/knowledge_mvp/PHASE_5C_FEW_SHOT_EXAMPLES.json`. These tests encode important **privacy-minimization guarantees** (forbidden strings like `192.168.50.225`, `/home/`, `cybernaif`, prompt-injection fragments must not appear in committed artifacts), so their failure also means those privacy assertions are currently unverified.
- **Evidence:** Reproduced with `python -m pytest -q` → `21 failed, 1229 passed, 305 skipped`. Confirmed the referenced files do not exist: `find docs/projects -name "*.json"` returns nothing; `docs/projects/` is an empty directory. The tests read pinned SHA-256 digests of files that are not present.
- **Remediation direction:** Restore the committed run-artifact fixtures (the JSON files under `docs/projects/{runs,llm_engines/runs,agent_lib/runs,knowledge_mvp}/`) into the repo, or move these pinned-byte tests behind a guard that skips when the fixture is absent (and regenerate the pinned digests). Do not weaken the privacy assertions.

### F2 (Low) — `check_publication_hygiene.py` cannot run in this environment
- **Where:** `scripts/check_publication_hygiene.py` (uses `git ls-files`).
- **Impact:** The hygiene gate errors out with `Referenced fixture files must be tracked` and lists many fixtures as "untracked." This is because the tree has no `.git` (verified: `git rev-parse --is-inside-work-tree` → fatal, not a repo). The tool's tracking check is therefore meaningless here; the reported "untracked" items are a byproduct of no git index, not necessarily real hygiene violations.
- **Evidence:** `python scripts/check_publication_hygiene.py` fails; `ls -la .git` → No such file or directory.
- **Remediation direction:** Run the hygiene check inside a proper git checkout. If the repo is intentionally delivered without `.git`, the tool should degrade gracefully (skip the git-tracking check when not in a repo) rather than report spurious failures.

## Rejected / Downgraded Hypotheses
- **"Library logic is broken"** — Downgraded. The 1,229 passing tests (spanning `llm_harness_core`, `llm_engines`, `engram`, `llm_inspector`, `llm_inspector_ui`, `agent_lib`, `rag_lib`, `action_trajectory_loop_guard`) exercise real code paths and pass. The failures are exclusively `FileNotFoundError` on missing fixture files, not assertion/logic failures in library code.
- **"Privacy boundary violated in committed artifacts"** — Downgraded/Rejected as a live defect. The privacy assertions are only failing because the artifact files they check are missing, not because a forbidden string is present. No evidence of an actual privacy leak.
- **"Fixture files exist but digests are stale"** — Rejected. The files do not exist at all (`docs/projects/` is empty), so this is missing data, not stale pins.

## Commands / Tests Run
- `python -m pytest -q` (repo root): `21 failed, 1229 passed, 305 skipped`.
- Per-package: `llm_harness_core` (28 passed), `engram` (230 passed, 7 skipped), `llm_inspector`/`llm_inspector_ui`/`agent_lib`/`rag_lib`/`action_trajectory_loop_guard` (only the pinned-byte/fixture tests fail).
- `llm_engines` (excluding network markers): `2 failed, 294 passed, 14 skipped` — the 2 failures are the missing `docs/projects/llm_engines/runs/*.json` files.
- Confirmed absence: `find docs/projects -name "*.json"` → empty; `docs/projects/` empty dir.
- Confirmed no git: `git rev-parse --is-inside-work-tree` → fatal; `.git` absent.
- `python scripts/check_publication_hygiene.py` → fails on git-tracking check.

## Remaining Uncertainty
- **High** regarding whether the missing fixtures are an artifact of this delivered copy or a genuine repo regression. The repo has no `.git`, so I cannot check history/blame to determine if `docs/projects/**/runs/*.json` were ever committed. If they were committed and then deleted, this is a real regression; if they were never meant to be in this tree, the pinned-byte tests should be guarded/skipped.
- The 21 failing tests are pinned-byte/fixture-dependent and cannot be validated without the fixture data; their correctness (and the privacy guarantees they encode) is therefore unverified in this environment.
- Uninspected: `examples/` (excluded from pytest collection), and any runtime behavior that requires network/live model access.

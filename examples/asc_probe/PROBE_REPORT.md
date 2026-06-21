# ASC Phase 0 Probe Report

Status: initial deterministic probe complete.

This report records read-and-test evidence for `SPEC-ASC-00-probe.md`. It does
not promote `agent_lib`; the package remains experimental.

## Part A: Worker/Mentor Loop Verification

| # | Constraint | Verdict | Evidence |
|---|---|---|---|
| 1 | Mentor optional/pluggable; worker runs alone | met | Read `agent_lib/src/agent_lib/runtime.py`: `AgentRuntime(..., critic=None)` is allowed and `_should_escalate` returns false without a critic. Read `agent_lib/src/agent_lib/llm_engines_adapter.py`: `RoleEngineSet` maps `critic` to the configured critic or planner fallback. Test evidence: `agent_lib/tests/test_runtime.py::test_runtime_invokes_tool_and_returns_final_output`, `test_runtime_escalates_to_critic_after_failed_tool_result`, and `examples/asc_probe/run_probe.py` worker-only vs worker-critic runs. |
| 2 | Escalation gated on objective signals, not worker self-report | met | Read `runtime._should_escalate`: escalation triggers on failed tool result, `action.meta["needs_critic"]`, or `observation.meta["needs_critic"]`. Read `ProgrammingFailureController`: failed `run_check` / `run_command` policy sets `_programming_next_controller = "critic"`. Test evidence: `test_runtime_escalates_to_critic_after_failed_tool_result` and `test_runtime_does_not_escalate_on_worker_self_report_without_objective_signal`. |
| 3 | Cost circuit-breaker caps mentor escalations per run | gap | Read `AgentRun.escalations` and `AgentRuntime.run`: escalations are counted, but there is no cap or stop condition tied to that count. Test evidence: `test_runtime_counts_but_does_not_cap_repeated_critic_escalations` reaches 3 escalations and stops only because the critic eventually returns final output. |
| 4 | Typed worker-to-mentor contract: approve / revise-with-guidance / redirect | gap | Read `contracts.py`: no critic feedback type exists. Read `runtime.py`: when escalated, `active_planner = self.critic`; the critic produces normal `AgentAction` objects. Test evidence: `test_runtime_critic_contract_is_implicit_planner_takeover_not_typed_feedback` accepts free-text critic guidance as a normal message action. |

## ADR-011 Isolation Questions

| Question | Answer | Evidence |
|---|---|---|
| Default isolation mode | `WorkspacePolicy.isolation_mode` defaults to `in_place`; command isolation defaults to host execution. | Read `WorkspacePolicy` defaults in `agent_lib/src/agent_lib/programming.py`. |
| Sandbox fallback reported as degraded, not clean success | met for metadata/interop: fallback may succeed but sets `sandbox_fallback_used=True` and trace/interop surfaces degraded state. It is not a hard stop. | Tests: `test_execute_workspace_command_can_fallback_to_host_when_requested`, `test_agent_red_team_lab.py::test_degraded_fallback_reports_degraded_success`, `test_agent_lib_interop_contracts.py::test_execute_workspace_command_interop_surfaces_degraded_fallback`. |
| Path resolution confined to workspace root | met by policy checks. | Test: `test_programming_tool_runtime_blocks_path_escape`. |
| Empty `writable_paths` means no write permission | met. | Test: `test_programming_tool_runtime_default_denies_writes_when_allowlist_empty`. |
| `runnable_commands` exact allowlist enforced | met. | Test: `test_programming_tool_runtime_enforces_command_allowlist`. |

## Part B: Deterministic Refactoring Probe

Fixture:
- `examples/asc_probe/fixture/text_tools.py`
- `examples/asc_probe/fixture/test_text_tools.py`

Harness:
- `examples/asc_probe/run_probe.py`
- Uses existing `AgentRuntime`, `SequencePlanner`, `FileWorkspace`, and `make_programming_tool_runtime`.
- Generated outputs are written under gitignored `examples/asc_probe/runs/`.

Observed ladder outcome from the initial run:

| Task | Tier | Worker-only | Worker+critic |
|---|---|---|---|
| `solo_extract_constant` | solo | `completed_solo` | `completed_solo` |
| `escalation_boundary_bug` | escalation | `failed_without_critic` | `escalated_recovered` |

No `wrong_but_tests_green` case was observed in this deterministic fixture.

## Forced Gaps

1. **Mentor escalation cap**: forced by Part A. The runtime can escalate repeatedly
   and has no cost ceiling. Build only when the next run needs bounded mentor
   cost rather than just observing escalation.
2. **Typed mentor feedback contract**: forced by Part A. The critic currently
   takes over as planner. Build only if a follow-up probe needs deterministic
   consume/approve/revise/redirect behavior rather than direct critic actions.

Part B did not force either gap beyond confirming the existing loop can recover
from objective verification failure in a low-stakes fixture.

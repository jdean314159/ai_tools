from __future__ import annotations

from agent_lib.eval import evaluate_lab, render_scenario, run_scenario


def test_blocked_command_reports_blocked_execution() -> None:
    run = run_scenario('blocked_command')
    assert run.trace_summary['blocked_count'] == 1
    assert 'tool_execution_blocked' in run.tool_operation['warnings']
    assert 'not allowed by workspace policy' in str(run.tool_result.output)


def test_approval_habituation_reports_approval_requirement() -> None:
    run = run_scenario('approval_habituation')
    assert run.trace_summary['approval_count'] == 1
    assert 'tool_approval_required' in run.tool_operation['warnings']
    assert 'proposal-only mode' in str(run.tool_result.output)


def test_degraded_fallback_reports_degraded_success() -> None:
    run = run_scenario('degraded_fallback')
    assert run.trace_summary['degraded_count'] == 1
    assert 'tool_execution_degraded' in run.tool_operation['warnings']
    assert 'sandbox smoke' in str(run.tool_result.output)


def test_render_and_evaluate_lab() -> None:
    rendered = render_scenario('degraded_fallback')
    assert 'Execution status:' in rendered
    report = evaluate_lab()
    assert all(item['passed'] for item in report['scenarios'].values())

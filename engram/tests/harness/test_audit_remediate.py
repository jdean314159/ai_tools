"""Tests for audit_memory() and audit_remediate() on ProjectMemory.

Verifies:
  1. audit_memory() returns an AuditReport.
  2. audit_remediate() defaults to dry_run=True.
  3. dry_run=True logs without mutating.
  4. dry_run=False executes tombstone on a synthesis rule.
  5. Unknown action lands in skipped, not errors.
  6. actions=None derives from report.findings.
  7. Result dict has correct keys.
"""

from __future__ import annotations

from .runner import test_group
from .mocks import TempDir, MockEngine, unique_session


def _make_pm(d):
    from engram.project_memory import ProjectMemory
    return ProjectMemory(
        project_id="audit_rem_test",
        project_type="general_assistant",
        base_dir=d,
        llm_engine=MockEngine(),
        session_id=unique_session(),
    )


def _store_rule(pm, rule_text: str) -> str:
    """Store a synthesis rule via payload dict; return its id."""
    from engram.memory.synthesis import SynthesisRule
    rule = SynthesisRule(
        rule_text=rule_text,
        support_episode_ids=["ep1", "ep2", "ep3"],
        support_count=3,
        confidence=0.75,
    )
    payload = rule.to_payload(project_id=pm.project_id)
    pm.semantic.store_synthesis_rule(payload, project_id=pm.project_id)
    return payload["id"]


# ── audit_memory ──────────────────────────────────────────────────────────────

@test_group("Audit Remediate")
def test_audit_memory_returns_report():
    """audit_memory() returns an AuditReport with expected attributes."""
    from engram.memory.audit import AuditReport
    with TempDir() as d:
        pm = _make_pm(d)
        report = pm.audit_memory()
        assert isinstance(report, AuditReport)
        assert hasattr(report, "findings")
        assert isinstance(report.findings, list)


@test_group("Audit Remediate")
def test_audit_memory_clean_db_has_no_errors():
    """Fresh empty database produces no error-severity findings."""
    with TempDir() as d:
        pm = _make_pm(d)
        report = pm.audit_memory()
        errors = [f for f in report.findings if f.severity == "error"]
        assert errors == [], f"Unexpected errors on clean DB: {errors}"


# ── audit_remediate result shape ──────────────────────────────────────────────

@test_group("Audit Remediate")
def test_remediate_result_has_correct_keys():
    """audit_remediate() result dict always has the four required keys."""
    with TempDir() as d:
        pm = _make_pm(d)
        report = pm.audit_memory()
        result = pm.audit_remediate(report, actions=[], dry_run=True)
        for key in ("applied", "skipped", "errors", "dry_run"):
            assert key in result, f"Missing key: {key!r}"


# ── dry_run behaviour ─────────────────────────────────────────────────────────

@test_group("Audit Remediate")
def test_dry_run_true_by_default():
    """dry_run defaults to True."""
    with TempDir() as d:
        pm = _make_pm(d)
        report = pm.audit_memory()
        result = pm.audit_remediate(report, actions=[("fake_id", "tombstone")])
        assert result["dry_run"] is True


@test_group("Audit Remediate")
def test_dry_run_does_not_delete_rule():
    """dry_run=True must not remove the rule from the database."""
    with TempDir() as d:
        pm = _make_pm(d)
        rule_id = _store_rule(pm, "Always use WAL mode for SQLite connections.")
        report = pm.audit_memory()
        pm.audit_remediate(report, actions=[(rule_id, "tombstone")], dry_run=True)

        rows = pm.semantic.search_synthesis_rules("WAL", limit=10)
        assert any(r.get("id") == rule_id for r in rows), (
            "dry_run=True deleted the rule — it must not mutate"
        )


# ── live remediation ──────────────────────────────────────────────────────────

@test_group("Audit Remediate")
def test_tombstone_removes_synthesis_rule():
    """dry_run=False + tombstone removes the synthesis rule from the DB."""
    with TempDir() as d:
        pm = _make_pm(d)
        rule_id = _store_rule(pm, "Use WAL mode on every SQLite connection at open time.")
        report = pm.audit_memory()
        result = pm.audit_remediate(
            report,
            actions=[(rule_id, "tombstone")],
            dry_run=False,
        )
        assert result["dry_run"] is False
        assert len(result["errors"]) == 0, f"Unexpected errors: {result['errors']}"

        rows = pm.semantic.search_synthesis_rules("WAL", limit=10)
        assert not any(r.get("id") == rule_id for r in rows), (
            "Rule still present after tombstone"
        )


# ── edge cases ────────────────────────────────────────────────────────────────

@test_group("Audit Remediate")
def test_unknown_action_goes_to_skipped():
    """Unrecognised action lands in skipped, not errors."""
    with TempDir() as d:
        pm = _make_pm(d)
        report = pm.audit_memory()
        result = pm.audit_remediate(
            report,
            actions=[("some_id", "nonexistent_action")],
            dry_run=False,
        )
        assert len(result["skipped"]) >= 1
        assert len(result["errors"]) == 0


@test_group("Audit Remediate")
def test_actions_none_derives_from_findings():
    """actions=None applies suggested_action from every finding."""
    with TempDir() as d:
        pm = _make_pm(d)
        report = pm.audit_memory()
        result = pm.audit_remediate(report, actions=None, dry_run=True)
        n_expected = sum(1 for f in report.findings if f.suggested_action)
        assert len(result["applied"]) == n_expected

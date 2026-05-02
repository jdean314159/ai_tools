"""Standalone tests for the audit/lint operation.

Validates each of the six audit checks plus the orchestrator. Uses real
SemanticMemory (with synthesis tables) and a lightweight mock episodic
layer so tests run fast without ChromaDB.

Run from engram/ root:
    PYTHONPATH=. python tests/harness/test_audit_standalone.py

Author: Jeffrey Dean
"""

import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engram.memory.semantic_memory import SemanticMemory
from engram.memory.synthesis import SynthesisRule, SynthesisRelation
from engram.memory import audit as audit_mod


PROJECT = "audit_test"


# --- Mock episodic layer -----------------------------------------------------

class MockEpisodic:
    """Just enough of EpisodicMemory to satisfy the audit checks."""
    def __init__(self, episode_ids: List[str]):
        self._episodes = [SimpleNamespace(id=eid) for eid in episode_ids]

    def get_recent_episodes(self, n=10000, days_back=3650, project_id=""):
        return list(self._episodes)


# --- Test runner -------------------------------------------------------------

class TestRunner:
    def __init__(self):
        self.passed = 0; self.failed = 0; self.errors = []

    def run(self, name, fn):
        try:
            fn(); self.passed += 1; print(f"  PASS  {name}")
        except AssertionError as e:
            self.failed += 1; msg = f"  FAIL  {name}: {e}"; self.errors.append(msg); print(msg)
        except Exception as e:
            self.failed += 1
            msg = f"  ERROR {name}: {type(e).__name__}: {e}"
            self.errors.append(msg); print(msg)

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'=' * 60}")
        print(f"Results: {self.passed}/{total} passed")
        if self.errors:
            for e in self.errors: print(e)
        return self.failed == 0


# --- Fixture helpers ---------------------------------------------------------

def fresh_semantic(tmpdir: str) -> SemanticMemory:
    return SemanticMemory(db_path=Path(tmpdir))


def write_rule(sm: SemanticMemory, text: str, support: List[str],
               confidence: float = 0.85, project_id: str = PROJECT) -> str:
    rule = SynthesisRule(
        rule_text=text,
        support_episode_ids=support,
        support_count=len(support),
        confidence=confidence,
    )
    payload = rule.to_payload(project_id)
    sm.store_synthesis_rule(payload, project_id=project_id)
    return payload["id"]


def write_relation(sm, rtype, subj, obj, source="", project_id=PROJECT):
    rel = SynthesisRelation(
        relation_type=rtype, subject_id=subj, object_id=obj,
        weight=1.0, source_synthesis_id=source or subj,
    )
    sm.store_synthesis_relation(rel.to_payload(), project_id=project_id)


def write_fact(sm: SemanticMemory, text: str, age_days: float = 0.0,
               project_id: str = PROJECT) -> str:
    """Insert a fact directly into the facts table with controllable timestamp."""
    import hashlib, json
    fact_id = f"fact_{hashlib.sha256(text.encode()).hexdigest()[:16]}"
    ts = time.time() - (age_days * 86400)
    sm._write_conn.execute(
        """INSERT OR REPLACE INTO facts
           (id, content, confidence, source, metadata, timestamp, user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (fact_id, text, 0.8, "test", json.dumps({}), ts, "test_user"),
    )
    sm._write_conn.commit()
    return fact_id


# --- Tests -------------------------------------------------------------------

def test_orphan_synthesis_all_missing():
    with tempfile.TemporaryDirectory() as td:
        sm = fresh_semantic(td)
        write_rule(sm, "Rule with all missing support",
                   support=["ep_dead_1", "ep_dead_2", "ep_dead_3"])
        report = audit_mod.run_audit(sm, MockEpisodic([]), PROJECT,
                                     checks=["orphan_synthesis"])
        findings = report.by_check("orphan_synthesis")
        assert len(findings) == 1, f"expected 1 finding, got {len(findings)}"
        assert findings[0].severity == "error"


def test_orphan_synthesis_partial_missing():
    with tempfile.TemporaryDirectory() as td:
        sm = fresh_semantic(td)
        write_rule(sm, "Partially supported rule",
                   support=["ep_alive", "ep_dead"])
        report = audit_mod.run_audit(sm, MockEpisodic(["ep_alive"]), PROJECT,
                                     checks=["orphan_synthesis"])
        findings = report.by_check("orphan_synthesis")
        assert len(findings) == 1
        assert findings[0].severity == "warn"


def test_orphan_synthesis_clean():
    with tempfile.TemporaryDirectory() as td:
        sm = fresh_semantic(td)
        write_rule(sm, "Fully supported rule",
                   support=["ep_a", "ep_b"])
        report = audit_mod.run_audit(
            sm, MockEpisodic(["ep_a", "ep_b"]), PROJECT,
            checks=["orphan_synthesis"],
        )
        assert len(report.findings) == 0


def test_contradicting_facts():
    with tempfile.TemporaryDirectory() as td:
        sm = fresh_semantic(td)
        # High lexical overlap, opposing polarity
        write_fact(sm, "WAL mode is always required for SQLite connections", age_days=30)
        time.sleep(0.01)  # ensure different timestamps
        write_fact(sm, "WAL mode is never required for SQLite connections", age_days=10)
        report = audit_mod.run_audit(
            sm, MockEpisodic([]), PROJECT,
            checks=["contradicting_facts"],
        )
        findings = report.by_check("contradicting_facts")
        assert len(findings) == 1, f"expected 1 contradiction, got {len(findings)}: {[f.details for f in findings]}"
        assert findings[0].severity == "warn"


def test_contradicting_facts_no_conflict():
    with tempfile.TemporaryDirectory() as td:
        sm = fresh_semantic(td)
        write_fact(sm, "WAL mode improves SQLite read concurrency")
        write_fact(sm, "Pragma journal_mode controls SQLite WAL behavior")
        report = audit_mod.run_audit(
            sm, MockEpisodic([]), PROJECT,
            checks=["contradicting_facts"],
        )
        # Different topics, no polarity conflict — should be empty
        assert len(report.by_check("contradicting_facts")) == 0


def test_stale_facts():
    with tempfile.TemporaryDirectory() as td:
        sm = fresh_semantic(td)
        write_fact(sm, "Old fact", age_days=200)
        write_fact(sm, "Recent fact", age_days=10)
        report = audit_mod.run_audit(
            sm, MockEpisodic([]), PROJECT,
            checks=["stale_facts"],
            stale_days=180,
        )
        findings = report.by_check("stale_facts")
        assert len(findings) == 1, f"expected 1 stale, got {len(findings)}"
        assert findings[0].severity == "info"
        assert findings[0].extra["age_days"] >= 180


def test_low_confidence_rules():
    with tempfile.TemporaryDirectory() as td:
        sm = fresh_semantic(td)
        write_rule(sm, "Strong rule", support=["e1", "e2", "e3"], confidence=0.9)
        write_rule(sm, "Weak rule", support=["e4", "e5", "e6"], confidence=0.5)
        report = audit_mod.run_audit(
            sm, MockEpisodic(["e1", "e2", "e3", "e4", "e5", "e6"]), PROJECT,
            checks=["low_confidence_rules"],
            confidence_threshold=0.65,
        )
        findings = report.by_check("low_confidence_rules")
        assert len(findings) == 1
        assert "Weak" in findings[0].extra["preview"]


def test_dangling_relations():
    with tempfile.TemporaryDirectory() as td:
        sm = fresh_semantic(td)
        rid = write_rule(sm, "Anchor rule", support=["ep_a"])
        write_relation(sm, "DERIVED_FROM", rid, "ep_a")          # valid
        write_relation(sm, "DERIVED_FROM", rid, "ep_ghost")      # dangling
        write_relation(sm, "RELATES_TO", "rule_ghost", rid)      # dangling
        report = audit_mod.run_audit(
            sm, MockEpisodic(["ep_a"]), PROJECT,
            checks=["dangling_relations"],
        )
        findings = report.by_check("dangling_relations")
        assert len(findings) == 2, f"expected 2 dangling, got {len(findings)}"


def test_near_duplicate_rules():
    with tempfile.TemporaryDirectory() as td:
        sm = fresh_semantic(td)
        # Same essential meaning, slight word variation, different IDs
        write_rule(sm, "Always set WAL mode on every SQLite connection",
                   support=["a", "b", "c"], confidence=0.8)
        write_rule(sm, "Always set WAL mode on each SQLite connection",
                   support=["a", "b", "c", "d"], confidence=0.9)
        report = audit_mod.run_audit(
            sm, MockEpisodic(["a", "b", "c", "d"]), PROJECT,
            checks=["near_duplicate_rules"],
            duplicate_overlap=0.6,
        )
        findings = report.by_check("near_duplicate_rules")
        assert len(findings) == 1, f"expected 1 duplicate, got {len(findings)}"
        # Weaker rule should be the suspect (the 0.8 confidence + 3 support one)
        assert findings[0].extra["similarity"] >= 0.6


def test_project_isolation():
    with tempfile.TemporaryDirectory() as td:
        sm = fresh_semantic(td)
        # Write orphans in a DIFFERENT project — should NOT appear in PROJECT audit
        write_rule(sm, "Other project rule",
                   support=["dead_other_1", "dead_other_2"],
                   project_id="other_project")
        report = audit_mod.run_audit(
            sm, MockEpisodic([]), PROJECT,
            checks=["orphan_synthesis"],
        )
        assert len(report.findings) == 0, \
            f"audit leaked across projects: {[f.to_dict() for f in report.findings]}"


def test_all_checks_run():
    with tempfile.TemporaryDirectory() as td:
        sm = fresh_semantic(td)
        report = audit_mod.run_audit(sm, MockEpisodic([]), PROJECT)
        # All 6 checks should have run on an empty DB without crashing
        assert len(report.checks_run) == 6, f"expected 6 checks, ran {report.checks_run}"
        assert report.elapsed_seconds >= 0


def test_report_markdown():
    with tempfile.TemporaryDirectory() as td:
        sm = fresh_semantic(td)
        write_rule(sm, "Bad rule", support=["dead_1", "dead_2", "dead_3"])
        report = audit_mod.run_audit(sm, MockEpisodic([]), PROJECT,
                                     checks=["orphan_synthesis"])
        md = report.to_markdown()
        assert "# Memory Audit" in md
        assert "ERROR" in md
        assert "orphan_synthesis" in md


def test_severity_sorting():
    with tempfile.TemporaryDirectory() as td:
        sm = fresh_semantic(td)
        # Mix of severities: orphan (error) + stale (info) + low_conf (info)
        write_rule(sm, "Orphan rule", support=["dead_1", "dead_2", "dead_3"],
                   confidence=0.9)
        write_fact(sm, "Old fact about something", age_days=200)
        write_rule(sm, "Weak rule", support=["e1", "e2", "e3"], confidence=0.4)
        report = audit_mod.run_audit(
            sm, MockEpisodic(["e1", "e2", "e3"]), PROJECT,
        )
        sorted_f = report.sorted_findings()
        # Errors must come before warns and infos
        if len(sorted_f) >= 2:
            severities = [f.severity for f in sorted_f]
            ranks = [audit_mod._SEVERITY_RANK[s] for s in severities]
            assert ranks == sorted(ranks), \
                f"findings not severity-sorted: {severities}"


def test_unknown_check_skipped():
    with tempfile.TemporaryDirectory() as td:
        sm = fresh_semantic(td)
        report = audit_mod.run_audit(sm, MockEpisodic([]), PROJECT,
                                     checks=["nonexistent_check"])
        assert "nonexistent_check" in report.checks_skipped
        assert report.checks_skipped["nonexistent_check"] == "unknown_check"


# --- Main --------------------------------------------------------------------

def main():
    runner = TestRunner()
    print("Memory audit standalone tests")
    print("=" * 60)

    print("\n[orphan_synthesis]")
    runner.run("test_orphan_synthesis_all_missing", test_orphan_synthesis_all_missing)
    runner.run("test_orphan_synthesis_partial_missing", test_orphan_synthesis_partial_missing)
    runner.run("test_orphan_synthesis_clean", test_orphan_synthesis_clean)

    print("\n[contradicting_facts]")
    runner.run("test_contradicting_facts", test_contradicting_facts)
    runner.run("test_contradicting_facts_no_conflict", test_contradicting_facts_no_conflict)

    print("\n[stale_facts]")
    runner.run("test_stale_facts", test_stale_facts)

    print("\n[low_confidence_rules]")
    runner.run("test_low_confidence_rules", test_low_confidence_rules)

    print("\n[dangling_relations]")
    runner.run("test_dangling_relations", test_dangling_relations)

    print("\n[near_duplicate_rules]")
    runner.run("test_near_duplicate_rules", test_near_duplicate_rules)

    print("\n[orchestrator]")
    runner.run("test_project_isolation", test_project_isolation)
    runner.run("test_all_checks_run", test_all_checks_run)
    runner.run("test_report_markdown", test_report_markdown)
    runner.run("test_severity_sorting", test_severity_sorting)
    runner.run("test_unknown_check_skipped", test_unknown_check_skipped)

    return 0 if runner.summary() else 1


if __name__ == "__main__":
    sys.exit(main())

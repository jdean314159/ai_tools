"""Standalone test for the synthesis layer — no LLM required.

Run from engram/ root:
    PYTHONPATH=. python tests/harness/test_synthesis_standalone.py
"""
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engram.memory.semantic_memory import SemanticMemory
from engram.memory.synthesis import SynthesisExtractor, SynthesisRule, SynthesisRelation

SAMPLE_EPISODES: List[Dict[str, Any]] = [
    {"id": "ep_001", "role": "user",
     "text": "Switched the SQLite connection to WAL mode and the locking errors went away.",
     "timestamp": time.time() - 7200},
    {"id": "ep_002", "role": "assistant",
     "text": "Good. WAL mode allows concurrent readers, which fixes the lock contention.",
     "timestamp": time.time() - 7100},
    {"id": "ep_003", "role": "user",
     "text": "Found another module without WAL pragma. Adding it now.",
     "timestamp": time.time() - 6900},
    {"id": "ep_004", "role": "user",
     "text": "Third connection without WAL mode caused the same locking issue.",
     "timestamp": time.time() - 6800},
    {"id": "ep_005", "role": "user",
     "text": "Auditing all SQLite connections now to ensure WAL is set.",
     "timestamp": time.time() - 6700},
]

# Rule 1: indices [0,2,3,4] = 4 episodes → passes min_support=3 ✓
# Rule 2: indices [0,3]     = 2 episodes → fails  min_support=3 ✗
# Expected: 1 rule emitted
MOCK_LLM_RESPONSE = """[
  {
    "rule": "Set WAL mode on every SQLite connection at open time, not just one",
    "support_indices": [0, 2, 3, 4],
    "confidence": 0.88
  },
  {
    "rule": "Locking errors usually point to missing journal_mode pragma",
    "support_indices": [0, 3],
    "confidence": 0.72
  }
]"""


class _TestRunner:
    def __init__(self):
        self.passed = 0; self.failed = 0; self.errors = []

    def run(self, name, fn):
        try:
            fn(); self.passed += 1; print(f"  PASS  {name}")
        except AssertionError as e:
            self.failed += 1; msg = f"  FAIL  {name}: {e}"; self.errors.append(msg); print(msg)
        except Exception as e:
            self.failed += 1; msg = f"  ERROR {name}: {type(e).__name__}: {e}"; self.errors.append(msg); print(msg)

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'=' * 60}")
        print(f"Results: {self.passed}/{total} passed")
        if self.errors:
            for e in self.errors: print(e)
        return self.failed == 0


def make_extractor(response=MOCK_LLM_RESPONSE):
    import threading
    ext = SynthesisExtractor.__new__(SynthesisExtractor)
    ext._engine_config = {"max_tokens": 1024, "temperature": 0.2}
    ext._min_support = 3
    ext._min_confidence = 0.6
    ext._engine = MagicMock()
    ext._engine.generate.return_value = response
    ext._lock = threading.Lock()
    ext._extractions = ext._rules_emitted = 0
    ext._rules_dropped_low_support = ext._rules_dropped_low_confidence = ext._errors = 0
    return ext


def test_extractor_parses_rules():
    result = make_extractor().extract(SAMPLE_EPISODES, project_id="testproj")
    assert not result.empty, f"expected non-empty, skipped={result.skipped_reason}"
    # Rule 2 has only 2 support_indices < min_support=3 → only 1 rule emitted
    assert len(result.rules) == 1, f"expected 1 rule, got {len(result.rules)}"
    assert result.rules[0].support_count == 4
    assert result.rules[0].confidence == 0.88
    assert "WAL" in result.rules[0].rule_text


def test_extractor_drops_low_support():
    bad = '[{"rule": "One-shot rule", "support_indices": [0], "confidence": 0.9}]'
    result = make_extractor(bad).extract(SAMPLE_EPISODES, project_id="testproj")
    assert len(result.rules) == 0
    assert make_extractor(bad)._rules_dropped_low_support == 0  # counter only on real run
    ext = make_extractor(bad)
    ext.extract(SAMPLE_EPISODES, project_id="testproj")
    assert ext.stats["rules_dropped_low_support"] == 1


def test_extractor_drops_low_confidence():
    bad = '[{"rule": "Low confidence", "support_indices": [0,1,2], "confidence": 0.4}]'
    ext = make_extractor(bad)
    result = ext.extract(SAMPLE_EPISODES, project_id="testproj")
    assert len(result.rules) == 0
    assert ext.stats["rules_dropped_low_confidence"] == 1


def test_extractor_window_too_small():
    result = make_extractor().extract(SAMPLE_EPISODES[:2], project_id="testproj")
    assert result.empty
    assert "window_too_small" in (result.skipped_reason or "")


def test_extractor_emits_relations():
    result = make_extractor().extract(SAMPLE_EPISODES, project_id="testproj")
    # Only rule 1 passes (4 episodes) → 4 DERIVED_FROM relations
    derived = [r for r in result.relations if r.relation_type == "DERIVED_FROM"]
    assert len(derived) == 4, f"expected 4 DERIVED_FROM, got {len(derived)}"


def test_rule_stable_id_is_idempotent():
    a = SynthesisRule(rule_text="Use WAL mode for all SQLite connections")
    b = SynthesisRule(rule_text="  use wal MODE for all SQLite connections  ")
    assert a.stable_id("p1") == b.stable_id("p1"), "case/whitespace should produce same id"
    assert a.stable_id("p1") != a.stable_id("p2"), "different projects → different ids"


def test_storage_round_trip():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SemanticMemory(db_path=Path(tmpdir))

        # Verify tables exist
        for table in ("synthesized_rules", "synthesized_relations"):
            row = sm._reader().execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            assert row is not None, f"{table} table missing — did you apply the schema patch?"

        rule = SynthesisRule(
            rule_text="Always run pip install -e . after editing pyproject.toml",
            support_episode_ids=["ep_a", "ep_b", "ep_c"],
            support_count=3, confidence=0.85,
        )
        payload = rule.to_payload(project_id="testproj")
        inserted = sm.store_synthesis_rule(payload, project_id="testproj")
        assert inserted is True

        hits = sm.search_synthesis_rules("pip install", project_id="testproj")
        assert len(hits) == 1, f"expected 1 hit, got {hits}"
        assert hits[0]["confidence"] == 0.85

        # Idempotency
        again = sm.store_synthesis_rule(payload, project_id="testproj")
        assert again is False
        assert sm.count_synthesis_rules(project_id="testproj") == 1

        # Relations
        rel = SynthesisRelation(
            relation_type="DERIVED_FROM", subject_id=payload["id"],
            object_id="ep_a", weight=0.85, source_synthesis_id=payload["id"],
        )
        sm.store_synthesis_relation(rel.to_payload(), project_id="testproj")
        relations = sm.get_relations_for(subject_id=payload["id"], project_id="testproj")
        assert len(relations) == 1
        assert relations[0]["object_id"] == "ep_a"


def test_storage_project_isolation():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SemanticMemory(db_path=Path(tmpdir))
        rule_a = SynthesisRule(rule_text="Project A rule about widgets")
        rule_b = SynthesisRule(rule_text="Project B rule about gadgets")
        sm.store_synthesis_rule(rule_a.to_payload("proj_a"), project_id="proj_a")
        sm.store_synthesis_rule(rule_b.to_payload("proj_b"), project_id="proj_b")
        assert len(sm.search_synthesis_rules("widgets", project_id="proj_a")) == 1
        assert len(sm.search_synthesis_rules("widgets", project_id="proj_b")) == 0


def main():
    runner = __TestRunner()
    print("Synthesis layer standalone tests")
    print("=" * 60)
    print("\n[Extractor logic]")
    runner.run("test_extractor_parses_rules", test_extractor_parses_rules)
    runner.run("test_extractor_drops_low_support", test_extractor_drops_low_support)
    runner.run("test_extractor_drops_low_confidence", test_extractor_drops_low_confidence)
    runner.run("test_extractor_window_too_small", test_extractor_window_too_small)
    runner.run("test_extractor_emits_relations", test_extractor_emits_relations)
    runner.run("test_rule_stable_id_is_idempotent", test_rule_stable_id_is_idempotent)
    print("\n[Storage round-trip]")
    runner.run("test_storage_round_trip", test_storage_round_trip)
    runner.run("test_storage_project_isolation", test_storage_project_isolation)
    return 0 if runner.summary() else 1


if __name__ == "__main__":
    sys.exit(main())

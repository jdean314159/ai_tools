#!/usr/bin/env python3
"""
engram test runner.

Usage:
    python run_tests.py              # Run all tests (skip Ollama)
    python run_tests.py --ollama     # Include Ollama integration tests
    python run_tests.py --verbose    # Show individual test names

Requirements:
    pip install pytest               # Preferred runner
    OR run this script directly (no pytest needed)
"""
from __future__ import annotations
import sys
import os
import time
import json
import uuid
import tempfile
import traceback
from pathlib import Path
from unittest.mock import MagicMock

# Ensure src is on the path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

# Try pytest first
try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

INCLUDE_OLLAMA = "--ollama" in sys.argv
VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv

# ---------------------------------------------------------------------------
# Minimal test harness (used when pytest is unavailable)
# ---------------------------------------------------------------------------

class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self._failures = []

    def run(self, name: str, fn, skip_reason: str = None):
        if skip_reason:
            if VERBOSE:
                print(f"  SKIP: {name} ({skip_reason})")
            self.skipped += 1
            return
        try:
            fn()
            if VERBOSE:
                print(f"  PASS: {name}")
            self.passed += 1
        except Exception as e:
            print(f"  FAIL: {name} — {e}")
            self._failures.append((name, traceback.format_exc()))
            self.failed += 1

    def report(self):
        total = self.passed + self.failed + self.skipped
        print(f"\n{'='*60}")
        print(f"Results: {self.passed}/{total} passed  |  "
              f"{self.failed} failed  |  {self.skipped} skipped")
        if self._failures:
            print("\nFailure details:")
            for name, tb in self._failures:
                print(f"\n--- {name} ---")
                print(tb)
        return self.failed == 0


def tmp():
    return Path(tempfile.mkdtemp())


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

def _import_all():
    from engram.retrieval.hybrid import reciprocal_rank_fusion, hybrid_episode_search
    from engram.embeddings.cache import EmbeddingCache, CachedEmbedder
    from engram.embeddings.base import EmbeddingResult
    from engram.semantic.graph import SemanticGraph
    from engram.semantic.forgetting import ForgettingConfig, ForgettingPolicy
    from engram.semantic.extractor import SemanticExtractor
    from engram.semantic.contradiction import detect_contradiction
    from engram.cli.migrate import migrate_paired_exchanges, migrate_semantic_graph
    from engram.storage.schema import SchemaManager
    from engram.version import SCHEMA_VERSION
    from engram import ProjectMemory
    from mock_helpers import MockEmbedder
    return {k: v for k, v in locals().items()}


# ---------------------------------------------------------------------------
# Test suites
# ---------------------------------------------------------------------------

def suite_rrf(r: TestRunner, ns: dict):
    rrf = ns["reciprocal_rank_fusion"]
    h = ns["hybrid_episode_search"]

    def single_list():
        result = rrf([[{"id": "a"}, {"id": "b"}, {"id": "c"}]])
        assert [x["id"] for x in result] == ["a", "b", "c"]
        assert result[0]["rrf_score"] > result[1]["rrf_score"] > result[2]["rrf_score"]

    def two_lists_agree():
        result = rrf([[{"id": "a"}, {"id": "b"}], [{"id": "a"}, {"id": "c"}]])
        assert result[0]["id"] == "a"

    def disjoint():
        result = rrf([[{"id": "a"}], [{"id": "b"}]])
        assert len(result) == 2
        assert abs(result[0]["rrf_score"] - result[1]["rrf_score"]) < 0.001

    def empty():
        assert rrf([]) == [] and rrf([[]]) == []

    def missing_id():
        result = rrf([[{"id": "a"}, {"no_id": "x"}, {"id": "b"}]])
        assert len(result) == 2

    def custom_k():
        items = [{"id": "a"}, {"id": "b"}]
        r60 = rrf([items], k=60)
        r1 = rrf([items], k=1)
        assert [x["id"] for x in r60] == [x["id"] for x in r1]
        assert r1[0]["rrf_score"] > r60[0]["rrf_score"]

    def preserves_data():
        result = rrf([[{"id": "a", "text": "hi", "importance": 0.9}]])
        assert result[0]["text"] == "hi" and "rrf_score" in result[0]

    def hybrid_none():
        assert h(query="t", query_embedding=None) == []

    def hybrid_text_only():
        now = time.time()
        result = h(query="t", query_embedding=None, text_results=[
            {"id": "a", "text": "t", "importance": 0.8, "created_at": now},
            {"id": "b", "text": "t", "importance": 0.5, "created_at": now},
        ])
        assert len(result) == 2 and all("final_score" in x for x in result)

    def hybrid_combined():
        now = time.time()
        vr = [{"id": "a", "text": "v", "importance": 0.5, "created_at": now},
              {"id": "b", "text": "both", "importance": 0.5, "created_at": now}]
        tr = [{"id": "b", "text": "both", "importance": 0.5, "created_at": now},
              {"id": "c", "text": "t", "importance": 0.5, "created_at": now}]
        result = h(query="t", query_embedding=[0.1]*8, vector_results=vr, text_results=tr)
        assert {x["id"] for x in result} == {"a", "b", "c"} and result[0]["id"] == "b"

    def recency_boost():
        now = time.time()
        result = h(query="t", query_embedding=None, recency_boost=True, text_results=[
            {"id": "r", "text": "t", "importance": 0.5, "created_at": now},
            {"id": "o", "text": "t", "importance": 0.5, "created_at": now - 60*86400},
        ])
        scores = {x["id"]: x["final_score"] for x in result}
        assert scores["r"] > scores["o"]

    def importance_boost():
        now = time.time()
        result = h(query="t", query_embedding=None, recency_boost=False, importance_boost=True,
                   text_results=[
                       {"id": "h", "text": "t", "importance": 1.0, "created_at": now},
                       {"id": "l", "text": "t", "importance": 0.0, "created_at": now},
                   ])
        scores = {x["id"]: x["final_score"] for x in result}
        ratio = scores["h"] / scores["l"]
        assert 1.4 < ratio < 1.6

    for name, fn in [
        ("single_list", single_list), ("two_lists_agree", two_lists_agree),
        ("disjoint", disjoint), ("empty", empty), ("missing_id", missing_id),
        ("custom_k", custom_k), ("preserves_data", preserves_data),
        ("hybrid_none", hybrid_none), ("hybrid_text_only", hybrid_text_only),
        ("hybrid_combined", hybrid_combined), ("recency_boost", recency_boost),
        ("importance_boost", importance_boost),
    ]:
        r.run(f"rrf/{name}", fn)


def suite_cache(r: TestRunner, ns: dict):
    EmbeddingCache = ns["EmbeddingCache"]
    CachedEmbedder = ns["CachedEmbedder"]
    EmbeddingResult = ns["EmbeddingResult"]
    MockEmbedder = ns["MockEmbedder"]

    def miss_none():
        assert EmbeddingCache(tmp() / "c.db").get("x", "m") is None

    def put_get():
        c = EmbeddingCache(tmp() / "c.db")
        emb = [0.1, 0.2]
        c.put(EmbeddingResult(text="hi", embedding=emb, model="m", dimension=2))
        assert c.get("hi", "m") == emb

    def models_isolated():
        c = EmbeddingCache(tmp() / "c.db")
        c.put(EmbeddingResult(text="t", embedding=[1.0], model="m:a", dimension=1))
        c.put(EmbeddingResult(text="t", embedding=[2.0], model="m:b", dimension=1))
        assert c.get("t", "m:a") == [1.0] and c.get("t", "m:b") == [2.0]

    def put_overwrites():
        c = EmbeddingCache(tmp() / "c.db")
        c.put(EmbeddingResult(text="t", embedding=[1.0], model="m", dimension=1))
        c.put(EmbeddingResult(text="t", embedding=[2.0], model="m", dimension=1))
        assert c.get("t", "m") == [2.0]

    def persists():
        p = tmp() / "c.db"
        EmbeddingCache(p).put(EmbeddingResult(text="p", embedding=[0.5], model="m", dimension=1))
        assert EmbeddingCache(p).get("p", "m") == [0.5]

    def stats():
        c = EmbeddingCache(tmp() / "c.db")
        for text, model in [("a", "m:1"), ("b", "m:1"), ("c", "m:2")]:
            c.put(EmbeddingResult(text=text, embedding=[1.0], model=model, dimension=1))
        s = c.get_stats()
        assert s["total_embeddings"] == 3 and s["unique_models"] == 2

    def hit_prevents_call():
        call_count = [0]
        class CE(MockEmbedder):
            def embed(self, text):
                call_count[0] += 1
                return super().embed(text)
        c = EmbeddingCache(tmp() / "c.db")
        ce = CachedEmbedder(CE(), c)
        r1 = ce.embed("test")
        assert call_count[0] == 1 and ce.misses == 1 and ce.hits == 0
        r2 = ce.embed("test")
        assert call_count[0] == 1 and ce.hits == 1
        assert r1.embedding == r2.embedding

    def batch_mixed():
        c = EmbeddingCache(tmp() / "c.db")
        e = MockEmbedder()
        c.put(e.embed("text_a"))
        ce = CachedEmbedder(e, c)
        result = ce.embed_batch(["text_a", "text_b", "text_c"])
        assert len(result.embeddings) == 3 and ce.hits == 1 and ce.misses == 2

    def dimension_passthrough():
        ce = CachedEmbedder(MockEmbedder(), EmbeddingCache(tmp() / "c.db"))
        assert ce.dimension == MockEmbedder.DIMENSION

    for name, fn in [
        ("miss_none", miss_none), ("put_get", put_get),
        ("models_isolated", models_isolated), ("put_overwrites", put_overwrites),
        ("persists", persists), ("stats", stats),
        ("hit_prevents_call", hit_prevents_call), ("batch_mixed", batch_mixed),
        ("dimension_passthrough", dimension_passthrough),
    ]:
        r.run(f"cache/{name}", fn)


def suite_forgetting(r: TestRunner, ns: dict):
    SemanticGraph = ns["SemanticGraph"]
    ForgettingConfig = ns["ForgettingConfig"]
    ForgettingPolicy = ns["ForgettingPolicy"]

    def af(g, fid, confidence=0.5, age_days=0, access_count=0, subject="s", value="v"):
        g.add_fact(fid, "preference", subject, value, confidence=confidence)
        now = time.time()
        past = now - age_days * 86400
        g.graph.nodes[fid]["created_at"] = past
        g.graph.nodes[fid]["accessed_at"] = past
        g.graph.nodes[fid]["access_count"] = access_count

    def config_valid():
        assert ForgettingConfig(decay_rate=0.9).decay_rate == 0.9

    def config_invalid():
        try:
            ForgettingConfig(decay_rate=1.5)
            assert False, "Should have raised"
        except ValueError:
            pass

    def config_defaults():
        c = ForgettingConfig()
        assert c.decay_rate == 0.95 and c.min_confidence == 0.1

    def decay_reduces():
        g = SemanticGraph()
        af(g, "f:1", confidence=1.0, age_days=14)
        g.decay_importance(decay_rate=0.5, period_days=7)
        assert abs(g.graph.nodes["f:1"]["confidence"] - 0.25) < 0.01

    def decay_recent_unchanged():
        g = SemanticGraph()
        af(g, "f:1", confidence=0.8, age_days=0)
        g.decay_importance(decay_rate=0.5, period_days=7)
        assert g.graph.nodes["f:1"]["confidence"] == 0.8

    def decay_floors_at_zero():
        g = SemanticGraph()
        af(g, "f:1", confidence=0.001, age_days=365)
        g.decay_importance(decay_rate=0.5, period_days=7)
        assert g.graph.nodes["f:1"]["confidence"] >= 0.0

    def prune_low_old():
        g = SemanticGraph()
        af(g, "f:p", confidence=0.05, age_days=40, access_count=0)
        af(g, "f:k", confidence=0.9)
        removed = g.forget_low_importance_facts(min_confidence=0.1, min_age_days=30)
        assert removed == 1 and not g.graph.has_node("f:p") and g.graph.has_node("f:k")

    def prune_preserves_accessed():
        g = SemanticGraph()
        af(g, "f:1", confidence=0.05, age_days=40)
        g.graph.nodes["f:1"]["accessed_at"] = time.time()
        g.graph.nodes["f:1"]["access_count"] = 5
        assert g.forget_low_importance_facts(min_confidence=0.1, min_age_days=30) == 0

    def prune_max_limit():
        g = SemanticGraph()
        for i in range(10):
            af(g, f"f:{i}", confidence=0.01, age_days=60, access_count=0)
        assert g.forget_low_importance_facts(min_confidence=0.1, min_age_days=30, max_to_prune=3) == 3

    def superseded_removes_old():
        g = SemanticGraph()
        af(g, "f:o"); af(g, "f:n")
        g.supersede_fact("f:o", "f:n")
        g.graph.nodes["f:o"]["superseded_at"] = time.time() - 91 * 86400
        assert g.forget_superseded_facts(min_age_days=90) == 1
        assert not g.graph.has_node("f:o") and g.graph.has_node("f:n")

    def superseded_keeps_recent():
        g = SemanticGraph()
        af(g, "f:o"); af(g, "f:n")
        g.supersede_fact("f:o", "f:n")
        assert g.forget_superseded_facts(min_age_days=90) == 0

    def policy_all():
        g = SemanticGraph()
        af(g, "f:p", confidence=0.01, age_days=60, access_count=0)
        af(g, "f:a", confidence=0.9)
        config = ForgettingConfig(enable_decay=True, decay_rate=0.5, decay_period_days=7,
                                   enable_pruning=True, min_confidence=0.1, min_age_days=30)
        stats = ForgettingPolicy(config).run_maintenance(g)
        assert stats["decayed"] == 1 and stats["pruned"] >= 1

    def policy_disabled():
        g = SemanticGraph()
        af(g, "f:l", confidence=0.01, age_days=60, access_count=0)
        config = ForgettingConfig(enable_decay=False, enable_pruning=False,
                                   enable_superseded_cleanup=False)
        stats = ForgettingPolicy(config).run_maintenance(g)
        assert stats["pruned"] == 0 and g.graph.has_node("f:l")

    def policy_saves():
        d = tmp()
        g = SemanticGraph(persist_path=d / "g.json")
        af(g, "f:1", confidence=0.9)
        ForgettingPolicy(ForgettingConfig()).run_maintenance(g)
        assert (d / "g.json").exists()

    for name, fn in [
        ("config_valid", config_valid), ("config_invalid", config_invalid),
        ("config_defaults", config_defaults), ("decay_reduces", decay_reduces),
        ("decay_recent_unchanged", decay_recent_unchanged),
        ("decay_floors_at_zero", decay_floors_at_zero),
        ("prune_low_old", prune_low_old),
        ("prune_preserves_accessed", prune_preserves_accessed),
        ("prune_max_limit", prune_max_limit),
        ("superseded_removes_old", superseded_removes_old),
        ("superseded_keeps_recent", superseded_keeps_recent),
        ("policy_all", policy_all), ("policy_disabled", policy_disabled),
        ("policy_saves", policy_saves),
    ]:
        r.run(f"forgetting/{name}", fn)


def suite_extraction(r: TestRunner, ns: dict):
    SemanticExtractor = ns["SemanticExtractor"]
    pe = lambda: SemanticExtractor(pattern_only=True)
    ef = lambda t: pe().extract(t).facts

    def prefer_for():
        assert any(f.fact_type == "preference" for f in ef("I prefer BeautifulSoup for HTML parsing."))

    def like_for():
        assert any(f.fact_type == "preference" for f in ef("We like FastAPI for building APIs."))

    def decided():
        assert any(f.fact_type == "decision" for f in ef("We decided to use PostgreSQL for the database."))

    def actually():
        assert any(f.fact_type == "correction" for f in ef("Actually, lxml is faster here."))

    def no_generic():
        assert len(ef("The weather is nice today.")) == 0

    def no_empty():
        assert len(ef("")) == 0

    def result_no_llm():
        assert pe().extract("I prefer Python for scripting.").llm_used is False

    def llm_fallback():
        resp = json.dumps([{"type": "preference", "subject": "deploy",
                            "value": "docker", "confidence": 0.8}])
        mock = MagicMock()
        mock.generate.return_value.message.content = resp
        result = SemanticExtractor(llm_engine=mock, enable_llm_extraction=True
                                   ).extract("We ship in containers.")
        assert result.llm_used and result.facts[0].value == "docker"

    def llm_empty():
        mock = MagicMock()
        mock.generate.return_value.message.content = "[]"
        assert SemanticExtractor(llm_engine=mock, enable_llm_extraction=True
                                 ).extract("Blue sky.").facts == []

    def llm_malformed():
        mock = MagicMock()
        mock.generate.return_value.message.content = "not json {{{"
        assert SemanticExtractor(llm_engine=mock, enable_llm_extraction=True
                                 ).extract("text.").facts == []

    def llm_markdown():
        resp = '```json\n[{"type":"decision","subject":"db","value":"pg","confidence":0.9}]\n```'
        mock = MagicMock()
        mock.generate.return_value.message.content = resp
        result = SemanticExtractor(llm_engine=mock, enable_llm_extraction=True
                                   ).extract("Which db to use.")
        assert result.llm_used and result.facts[0].value == "pg"

    def llm_disabled():
        mock = MagicMock()
        SemanticExtractor(llm_engine=mock, enable_llm_extraction=False).extract("text.")
        mock.generate.assert_not_called()

    def llm_failure():
        mock = MagicMock()
        mock.generate.side_effect = RuntimeError("down")
        assert SemanticExtractor(llm_engine=mock, enable_llm_extraction=True
                                 ).extract("text.").facts == []

    for name, fn in [
        ("prefer_for", prefer_for), ("like_for", like_for),
        ("decided", decided), ("actually", actually),
        ("no_generic", no_generic), ("no_empty", no_empty),
        ("result_no_llm", result_no_llm), ("llm_fallback", llm_fallback),
        ("llm_empty", llm_empty), ("llm_malformed", llm_malformed),
        ("llm_markdown", llm_markdown), ("llm_disabled", llm_disabled),
        ("llm_failure", llm_failure),
    ]:
        r.run(f"extraction/{name}", fn)


def suite_migration(r: TestRunner, ns: dict):
    migrate_paired_exchanges = ns["migrate_paired_exchanges"]
    migrate_semantic_graph = ns["migrate_semantic_graph"]
    SchemaManager = ns["SchemaManager"]
    SCHEMA_VERSION = ns["SCHEMA_VERSION"]

    def make_project(base_dir):
        pd = base_dir / "project"
        pd.mkdir(parents=True)
        (pd / "sessions").mkdir()
        episodes = [
            {"id": f"ep_{uuid.uuid4().hex[:8]}",
             "text": "I prefer BeautifulSoup for HTML parsing.",
             "importance": 0.8, "created_at": time.time(),
             "metadata": {"role": "user", "session_id": "s1"}},
            {"id": f"ep_{uuid.uuid4().hex[:8]}",
             "text": "We decided to use PostgreSQL for the main database.",
             "importance": 0.9, "created_at": time.time(),
             "metadata": {"role": "user", "session_id": "s1"}},
        ]
        with (pd / "episodes.jsonl").open("w") as f:
            for ep in episodes:
                f.write(json.dumps(ep) + "\n")
        session1 = [
            {"role": "user", "text": "What library for HTML?"},
            {"role": "assistant", "text": "BeautifulSoup."},
            {"role": "user", "text": "And the database?"},
            {"role": "assistant", "text": "PostgreSQL."},
        ]
        with (pd / "sessions" / "s1.jsonl").open("w") as f:
            for t in session1:
                f.write(json.dumps(t) + "\n")
        return pd

    def paired_basic():
        assert migrate_paired_exchanges(make_project(tmp())) == 2

    def paired_format():
        pd = make_project(tmp())
        migrate_paired_exchanges(pd)
        episodes = []
        with (pd / "episodes.jsonl").open() as f:
            for line in f:
                if line.strip():
                    episodes.append(json.loads(line))
        paired = [ep for ep in episodes if ep.get("metadata", {}).get("type") == "exchange"]
        assert all(ep["text"].startswith("User: ") and "\nAssistant: " in ep["text"]
                   for ep in paired)

    def no_sessions():
        pd = tmp() / "project"
        pd.mkdir(parents=True)
        (pd / "episodes.jsonl").write_text("")
        assert migrate_paired_exchanges(pd) == 0

    def semantic_creates_graph():
        pd = make_project(tmp())
        migrate_semantic_graph(pd, llm_engine=None)
        assert (pd / "semantic_graph.json").exists()

    def schema_sets():
        pd = make_project(tmp())
        mgr = SchemaManager(pd)
        mgr.set_version(SCHEMA_VERSION)
        assert mgr.get_version() == SCHEMA_VERSION
        assert not mgr.needs_migration(SCHEMA_VERSION)

    def schema_detects_old():
        pd = tmp() / "project"
        pd.mkdir()
        SchemaManager(pd).set_version("1.0")
        assert SchemaManager(pd).needs_migration(SCHEMA_VERSION)

    def schema_no_file():
        mgr = SchemaManager(tmp() / "project")
        assert mgr.get_version() is None and mgr.needs_migration("2.0")

    def schema_reload():
        pd = tmp() / "project"
        pd.mkdir()
        SchemaManager(pd).set_version("2.0")
        assert SchemaManager(pd).get_version() == "2.0"

    for name, fn in [
        ("paired_basic", paired_basic), ("paired_format", paired_format),
        ("no_sessions", no_sessions), ("semantic_creates_graph", semantic_creates_graph),
        ("schema_sets", schema_sets), ("schema_detects_old", schema_detects_old),
        ("schema_no_file", schema_no_file), ("schema_reload", schema_reload),
    ]:
        r.run(f"migration/{name}", fn)


def suite_core(r: TestRunner, ns: dict):
    ProjectMemory = ns["ProjectMemory"]
    SemanticGraph = ns["SemanticGraph"]
    detect_contradiction = ns["detect_contradiction"]

    def build_prompt():
        mem = ProjectMemory(session_id="s1")
        mem.add_turn("user", "Hola", session_id="s1")
        mem.add_turn("assistant", "Como estas?", session_id="s1")
        result = mem.build_prompt("Cuentame mas.")
        assert "Hola" in result["prompt"] and result["memory_tokens"] >= 2

    def episode_stats():
        mem = ProjectMemory(session_id="s1")
        eid = mem.store_episode(
            "Session summary: practiced greetings and conversation.",
            metadata={"type": "session_summary"}, importance=0.95,
        )
        results = mem.search_episodes("summary", n=5, min_importance=0.5)
        stats = mem.get_stats()
        assert eid and results and stats["backend"] == "engram"

    def persistence():
        with tempfile.TemporaryDirectory() as d:
            m1 = ProjectMemory(base_dir=d, project_id="proj", session_id="s1")
            m1.add_turn("user", "Hola estoy aprendiendo espanol.", session_id="s1")
            m1.add_turn("assistant", "Muy bien, sigamos practicando.", session_id="s1")
            eid = m1.store_episode(
                "Session summary: practiced greetings and present tense.",
                metadata={"type": "session_summary"}, importance=0.95,
            )
            m1.close()
            m2 = ProjectMemory(base_dir=d, project_id="proj", session_id="s1")
            turns = m2.get_recent_turns("s1", limit=10)
            eps = m2.search_episodes("session summary", n=5, min_importance=0.5)
            m2.close()
            assert eid and [t["role"] for t in turns] == ["user", "assistant"]
            assert eps and "practiced greetings" in eps[0].text

    def pairing():
        with tempfile.TemporaryDirectory() as d:
            mem = ProjectMemory(base_dir=d, project_id="p", session_id="s1",
                                auto_pair_assistant=True)
            mem.add_turn("user", "What is Python?", "s1")
            mem.add_turn("assistant", "Python is a programming language.", "s1")
            assert mem.get_stats()["episodic"]["pairing"]["paired_exchanges"] == 1
            assert any("User:" in r.text for r in mem.search_episodes("Python", n=5))
            mem.close()

    def orphan():
        with tempfile.TemporaryDirectory() as d:
            mem = ProjectMemory(base_dir=d, project_id="p", session_id="s1",
                                auto_pair_assistant=True, orphan_assistant_handling="skip")
            mem.add_turn("assistant", "Hello orphan.", "s1")
            assert mem.get_stats()["episodic"]["pairing"]["orphan_assistants"] == 1
            mem.close()

    def delete_episode():
        with tempfile.TemporaryDirectory() as d:
            with ProjectMemory(base_dir=d, project_id="p", session_id="s1") as mem:
                eid = mem.store_episode(
                    "This test episode about databases will be deleted.",
                    importance=0.9, bypass_filter=True,
                )
                count_before = len(mem._episodes)
                assert mem.delete_episode(eid) is True
                assert len(mem._episodes) == count_before - 1

    def delete_nonexistent():
        with tempfile.TemporaryDirectory() as d:
            with ProjectMemory(base_dir=d, project_id="p", session_id="s1") as mem:
                assert mem.delete_episode("ep_nonexistent") is False

    def forget_session():
        with tempfile.TemporaryDirectory() as d:
            with ProjectMemory(base_dir=d, project_id="p", session_id="s1") as mem:
                mem.add_turn("user", "Turn in session to forget about things.", "s1")
                mem.add_turn("assistant", "Acknowledged the session content.", "s1")
                result = mem.forget_session("s1")
                assert result["turns_removed"] >= 2 and "s1" not in mem._sessions

    def forget_user_data():
        with tempfile.TemporaryDirectory() as d:
            with ProjectMemory(base_dir=d, project_id="p", session_id="s1") as mem:
                mem.store_episode(
                    "Important project data about machine learning systems.",
                    importance=0.9, bypass_filter=True,
                )
                assert len(mem._episodes) > 0
                result = mem.forget_user_data()
                assert result["episodes_removed"] > 0 and len(mem._episodes) == 0

    def writer_lock_live():
        with tempfile.TemporaryDirectory() as d:
            with ProjectMemory(base_dir=d, project_id="p", session_id="s1") as m1:
                try:
                    m2 = ProjectMemory(base_dir=d, project_id="p", session_id="s2")
                    m2.close()
                    assert False, "Should have raised"
                except RuntimeError as e:
                    assert "lock" in str(e).lower()

    def stale_lock_cleared():
        with tempfile.TemporaryDirectory() as d:
            Path(d, "p").mkdir(parents=True)
            (Path(d, "p") / ".writer.lock").write_text("999999\n")
            with ProjectMemory(base_dir=d, project_id="p", session_id="s1") as mem:
                assert mem._writer_lock is not None

    def semantic_graph():
        with tempfile.TemporaryDirectory() as d:
            g = SemanticGraph(persist_path=Path(d) / "g.json")
            g.add_fact("fact:001", "preference", "parsing", "beautifulsoup", confidence=0.8)
            assert g.query_facts(subject="parsing")[0]["value"] == "beautifulsoup"
            g.save()
            g2 = SemanticGraph(persist_path=Path(d) / "g.json")
            assert g2.query_facts(subject="parsing")[0]["value"] == "beautifulsoup"

    def contradiction():
        existing = [{"id": "f:001", "subject": "lib", "value": "requests",
                     "fact_type": "preference"}]
        assert detect_contradiction(
            {"subject": "lib", "value": "httpx", "fact_type": "preference"}, existing
        ) == "f:001"
        assert detect_contradiction(
            {"subject": "lib", "value": "requests", "fact_type": "preference"}, existing
        ) is None

    def malformed_jsonl():
        with tempfile.TemporaryDirectory() as d:
            ep_path = Path(d) / "proj" / "episodes.jsonl"
            Path(d, "proj").mkdir()
            ep_path.write_text(
                '{"id":"ep_001","text":"valid episode one here","importance":0.8,"created_at":1000}\n'
                'this is not json\n'
                '{"id":"ep_002","text":"valid episode two here","importance":0.7,"created_at":1001}\n'
            )
            mem = ProjectMemory(base_dir=d, project_id="proj", session_id="s1")
            assert len(mem._episodes) == 2
            mem.close()

    def corrupted_graph():
        with tempfile.TemporaryDirectory() as d:
            gp = Path(d) / "proj" / "semantic_graph.json"
            Path(d, "proj").mkdir()
            gp.write_text("not json {{{")
            mem = ProjectMemory(base_dir=d, project_id="proj", session_id="s1",
                                enable_semantic_graph=True)
            assert mem.semantic is not None
            assert mem.semantic.graph.number_of_nodes() == 0
            assert gp.with_suffix(".json.corrupted").exists()
            mem.close()

    for name, fn in [
        ("build_prompt", build_prompt), ("episode_stats", episode_stats),
        ("persistence", persistence), ("pairing", pairing), ("orphan", orphan),
        ("delete_episode", delete_episode), ("delete_nonexistent", delete_nonexistent),
        ("forget_session", forget_session), ("forget_user_data", forget_user_data),
        ("writer_lock_live", writer_lock_live), ("stale_lock_cleared", stale_lock_cleared),
        ("semantic_graph", semantic_graph), ("contradiction", contradiction),
        ("malformed_jsonl", malformed_jsonl), ("corrupted_graph", corrupted_graph),
    ]:
        r.run(f"core/{name}", fn)


def suite_ollama(r: TestRunner, ns: dict):
    """Integration tests requiring Ollama. Skipped unless --ollama passed."""

    def _ollama_available():
        try:
            import requests
            return requests.get("http://localhost:11434/api/tags", timeout=3).status_code == 200
        except Exception:
            return False

    def _model_available(model):
        try:
            import requests
            tags = requests.get("http://localhost:11434/api/tags", timeout=3).json().get("models", [])
            return any(m.get("name", "").startswith(model.split(":")[0]) for m in tags)
        except Exception:
            return False

    if not INCLUDE_OLLAMA:
        r.run("ollama/skipped", lambda: None,
              skip_reason="Pass --ollama to run integration tests")
        return

    if not _ollama_available():
        r.run("ollama/all", lambda: None,
              skip_reason="Ollama not running at localhost:11434")
        return

    if not _model_available("nomic-embed-text"):
        r.run("ollama/all", lambda: None,
              skip_reason="nomic-embed-text not pulled (run: ollama pull nomic-embed-text)")
        return

    from engram.embeddings.ollama import OllamaEmbedder
    from engram import ProjectMemory

    def embedder_dimension():
        e = OllamaEmbedder(model="nomic-embed-text")
        result = e.embed("test text for dimension check")
        assert len(result.embedding) == 768

    def full_workflow():
        e = OllamaEmbedder(model="nomic-embed-text")
        with tempfile.TemporaryDirectory() as d:
            mem = ProjectMemory(
                base_dir=d, project_id="ollama_test", session_id="s1",
                embedder=e, auto_pair_assistant=True,
            )
            mem.add_turn("user", "I am building a web scraper for job listings.", "s1")
            mem.add_turn("assistant", "Are you using BeautifulSoup?", "s1")
            mem.add_turn("user", "I prefer BeautifulSoup for its simplicity.", "s1")
            mem.add_turn("assistant", "Good choice for static HTML.", "s1")
            results = mem.search_episodes("HTML parsing library", n=5)
            assert len(results) > 0
            assert mem.get_stats()["vector_search"]["available"] is True
            mem.close()

    def embedding_cache():
        from engram.embeddings.cache import EmbeddingCache, CachedEmbedder
        e = OllamaEmbedder(model="nomic-embed-text")
        with tempfile.TemporaryDirectory() as d:
            cached = CachedEmbedder(e, EmbeddingCache(Path(d) / "cache.db"))
            text = "Unique cache verification sentence."
            cached.embed(text)
            assert cached.misses == 1 and cached.hits == 0
            cached.embed(text)
            assert cached.hits == 1 and cached.misses == 1

    def dimension_mismatch():
        from engram.storage.chromadb_store import DimensionMismatchError
        from engram import ProjectMemory
        from mock_helpers import MockEmbedder
        e = OllamaEmbedder(model="nomic-embed-text")
        with tempfile.TemporaryDirectory() as d:
            mem = ProjectMemory(base_dir=d, project_id="dim_test", session_id="s1", embedder=e)
            mem.store_episode("Testing dimension mismatch with real embedder.",
                              importance=0.8, bypass_filter=True)
            mem.close()
            try:
                mem2 = ProjectMemory(base_dir=d, project_id="dim_test", session_id="s1",
                                     embedder=MockEmbedder())
                mem2.close()
                assert False, "Should have raised DimensionMismatchError"
            except DimensionMismatchError:
                pass

    for name, fn in [
        ("embedder_dimension", embedder_dimension),
        ("full_workflow", full_workflow),
        ("embedding_cache", embedding_cache),
        ("dimension_mismatch", dimension_mismatch),
    ]:
        r.run(f"ollama/{name}", fn)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if HAS_PYTEST and not ("--no-pytest" in sys.argv):
        # Prefer pytest when available
        args = [str(ROOT / "tests"), "-v" if VERBOSE else "-q"]
        if not INCLUDE_OLLAMA:
            args += ["--ignore", str(ROOT / "tests" / "test_ollama_integration.py")]
        sys.exit(pytest.main(args))

    # Fallback: run directly
    print("engram Test Runner")
    print(f"{'='*60}")

    try:
        ns = _import_all()
    except ImportError as e:
        print(f"FATAL: Import failed — {e}")
        print("Make sure PYTHONPATH includes src/ and llm_harness_core/src/")
        sys.exit(1)

    r = TestRunner()

    suites = [
        ("RRF", suite_rrf),
        ("Embedding Cache", suite_cache),
        ("Forgetting", suite_forgetting),
        ("Fact Extraction", suite_extraction),
        ("Migration", suite_migration),
        ("Core", suite_core),
        ("Ollama Integration", suite_ollama),
    ]

    for suite_name, suite_fn in suites:
        print(f"\n--- {suite_name} ---")
        suite_fn(r, ns)

    success = r.report()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

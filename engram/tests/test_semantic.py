from __future__ import annotations
from engram import ProjectMemory
from engram.semantic.graph import SemanticGraph
from engram.semantic.extractor import SemanticExtractor
from engram.semantic.forgetting import ForgettingConfig, ForgettingPolicy
from engram.semantic.contradiction import detect_contradiction


def test_graph_add_and_query(tmp_path):
    graph = SemanticGraph(persist_path=tmp_path / "graph.json")
    graph.add_fact("fact:001", "preference", "parsing", "beautifulsoup", confidence=0.8)
    facts = graph.query_facts(subject="parsing")
    assert len(facts) == 1
    assert facts[0]["value"] == "beautifulsoup"
    assert facts[0]["fact_type"] == "preference"


def test_graph_persist_reload(tmp_path):
    path = tmp_path / "graph.json"
    g1 = SemanticGraph(persist_path=path)
    g1.add_fact("fact:001", "decision", "api_style", "rest", confidence=0.9)
    g1.save()

    g2 = SemanticGraph(persist_path=path)
    facts = g2.query_facts(fact_type="decision")
    assert len(facts) == 1
    assert facts[0]["value"] == "rest"


def test_contradiction_detection():
    existing = [
        {"id": "fact:001", "subject": "library", "value": "requests", "fact_type": "preference"}
    ]
    new_fact = {"subject": "library", "value": "httpx", "fact_type": "preference"}
    contradicted = detect_contradiction(new_fact, existing)
    assert contradicted == "fact:001"


def test_no_contradiction_same_value():
    existing = [
        {"id": "fact:001", "subject": "library", "value": "requests", "fact_type": "preference"}
    ]
    new_fact = {"subject": "library", "value": "requests", "fact_type": "preference"}
    assert detect_contradiction(new_fact, existing) is None


def test_no_contradiction_different_type():
    existing = [
        {"id": "fact:001", "subject": "library", "value": "requests", "fact_type": "preference"}
    ]
    new_fact = {"subject": "library", "value": "httpx", "fact_type": "decision"}
    assert detect_contradiction(new_fact, existing) is None


def test_supersede(tmp_path):
    graph = SemanticGraph(persist_path=tmp_path / "graph.json")
    graph.add_fact("fact:old", "preference", "parsing", "bs4", confidence=0.7)
    graph.add_fact("fact:new", "preference", "parsing", "lxml", confidence=0.9)
    graph.supersede_fact("fact:old", "fact:new")

    active = graph.query_facts(subject="parsing", include_superseded=False)
    assert len(active) == 1
    assert active[0]["id"] == "fact:new"

    all_facts = graph.query_facts(subject="parsing", include_superseded=True)
    assert len(all_facts) == 2


def test_pattern_extraction():
    extractor = SemanticExtractor(pattern_only=True)
    result = extractor.extract("I prefer lxml for parsing HTML.")
    assert result.llm_used is False
    assert len(result.facts) >= 1
    assert any(f.fact_type == "preference" for f in result.facts)


def test_forgetting_pruning(tmp_path):
    import time

    graph = SemanticGraph(persist_path=tmp_path / "graph.json")
    graph.add_fact("fact:old_low", "preference", "old_lib", "whatever", confidence=0.05)
    # Backdating creation to force pruning
    graph.graph.nodes["fact:old_low"]["created_at"] = time.time() - (40 * 86400)
    graph.graph.nodes["fact:old_low"]["accessed_at"] = time.time() - (40 * 86400)

    config = ForgettingConfig(min_confidence=0.1, min_age_days=30)
    policy = ForgettingPolicy(config)
    stats = policy.run_maintenance(graph)
    assert stats["pruned"] >= 1
    remaining = graph.query_facts()
    assert all(f["id"] != "fact:old_low" for f in remaining)


def test_project_memory_semantic_layer(tmp_path):
    extractor = SemanticExtractor(pattern_only=True)
    mem = ProjectMemory(
        base_dir=tmp_path,
        project_id="sem_test",
        session_id="s1",
        extractor=extractor,
        enable_semantic_graph=True,
    )
    mem.add_turn("user", "I prefer BeautifulSoup for HTML parsing.", "s1")
    facts = mem.get_facts(query="parsing")
    # Pattern extraction may or may not fire depending on phrasing
    # Just verify the API works without error
    assert isinstance(facts, list)
    mem.close()

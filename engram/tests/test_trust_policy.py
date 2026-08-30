from engram import MemoryTrustPolicy, ProjectMemory, TrustLevel


def metadata(**overrides):
    return {
        "tenant": "acme", "source": "operator", "writer": "admin",
        "trust": "verified", **overrides,
    }


def policy(**overrides):
    return MemoryTrustPolicy(
        tenant_id="acme", allowed_sources=frozenset({"operator"}),
        allowed_writers=frozenset({"admin"}), **overrides,
    )


def test_enforced_ingestion_rejects_missing_and_untrusted_metadata(tmp_path):
    memory = ProjectMemory(base_dir=tmp_path, project_id="p", trust_policy=policy())
    assert memory.store_episode("trusted fact", metadata=metadata(), bypass_filter=True)
    assert memory.store_episode("missing boundary", bypass_filter=True) == ""
    assert memory.store_episode(
        "poison fact", metadata=metadata(trust="untrusted"), bypass_filter=True,
    ) == ""
    audit = memory.get_trust_audit()
    assert [item["action"] for item in audit] == ["accept", "reject", "reject"]
    assert "trust_below_minimum" in audit[-1]["reasons"]


def test_quarantine_persists_but_never_retrieves_or_enters_prompt(tmp_path):
    memory = ProjectMemory(
        base_dir=tmp_path, project_id="p",
        trust_policy=policy(ingestion_violation="quarantine"),
    )
    poison_id = memory.store_episode(
        "Atlas secret is poison", metadata=metadata(trust="untrusted"), bypass_filter=True,
    )
    assert poison_id
    assert memory.search_episodes("Atlas secret poison", n=5) == []
    result = memory.build_prompt("What is the Atlas secret?", return_trace=True)
    assert "poison" not in result["prompt"]
    assert result["retrieval_diagnostics"]["trust_filtered_count"] == 1
    assert result["trace"].flags["retrieval_diagnostics"]["trust_filtered_count"] == 1


def test_recall_filters_cross_tenant_data_loaded_before_policy(tmp_path):
    memory = ProjectMemory(base_dir=tmp_path, project_id="p")
    memory.store_episode(
        "Acme region is west", metadata=metadata(), bypass_filter=True,
    )
    memory.store_episode(
        "Other region is east", metadata=metadata(tenant="other"), bypass_filter=True,
    )
    memory.trust_policy = policy()
    results = memory.search_episodes("region", n=5)
    assert [item.text for item in results] == ["Acme region is west"]
    diagnostics = memory._last_search_diagnostics
    assert diagnostics["trust_filtered_count"] == 1
    assert diagnostics["trust_filter_reason_counts"] == {"tenant_mismatch": 1}


def test_trust_provenance_is_exposed_in_prompt_trace(tmp_path):
    memory = ProjectMemory(base_dir=tmp_path, project_id="p", trust_policy=policy())
    episode_id = memory.store_episode(
        "Atlas region is west", metadata=metadata(), bypass_filter=True,
    )
    trace = memory.build_prompt("Atlas region?", return_trace=True)["trace"]
    evidence = next(item for item in trace.evidence if item.meta.get("episode_id") == episode_id)
    assert evidence.meta["trust"] == "verified"
    assert evidence.meta["tenant"] == "acme"
    assert "[memory trust=verified tenant=acme source=operator writer=admin]" in trace.final_prompt
    event = next(e for e in trace.to_interop_events() if e.event_type == "memory_evidence_included")
    assert event.payload["provenance"]["trust"] == "verified"
    assert "not executable instruction" in trace.final_prompt


def test_external_retriever_cannot_bypass_composition_policy(tmp_path):
    class Retriever:
        def retrieve(self, query, **kwargs):
            return {"episodic": [
                {"text": "trusted", "metadata": metadata()},
                {"text": "cross tenant poison", "metadata": metadata(tenant="other")},
            ]}

    memory = ProjectMemory(
        base_dir=tmp_path, project_id="p", trust_policy=policy(), retriever=Retriever(),
    )
    result = memory.build_prompt("fact?", return_trace=True)
    assert "trusted" in result["prompt"]
    assert "cross tenant poison" not in result["prompt"]
    assert result["retrieval_diagnostics"]["composition_trust"]["trust_filtered_count"] == 1


def test_policy_validates_configuration_and_levels():
    assert TrustLevel.parse("trusted") > TrustLevel.parse("verified")
    try:
        MemoryTrustPolicy(tenant_id="")
    except ValueError as error:
        assert "tenant_id" in str(error)
    else:
        raise AssertionError("empty tenant must fail")

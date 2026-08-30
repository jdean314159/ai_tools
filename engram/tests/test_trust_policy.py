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


def test_composed_provenance_label_includes_application_evidence_id(tmp_path):
    memory = ProjectMemory(base_dir=tmp_path, project_id="p", trust_policy=policy())
    memory.store_episode(
        "Atlas region is west", metadata=metadata(evidence_id="ATLAS-7"),
        bypass_filter=True,
    )
    prompt = memory.build_prompt("Atlas region?")["prompt"]
    assert "[memory evidence_id=ATLAS-7 trust=verified" in prompt


def test_policy_validates_configuration_and_levels():
    assert TrustLevel.parse("trusted") > TrustLevel.parse("verified")
    try:
        MemoryTrustPolicy(tenant_id="")
    except ValueError as error:
        assert "tenant_id" in str(error)
    else:
        raise AssertionError("empty tenant must fail")


def test_explicit_tenant_alias_is_authorized(tmp_path):
    memory = ProjectMemory(
        base_dir=tmp_path, project_id="p",
        trust_policy=policy(tenant_aliases=frozenset({"acme-legacy"})),
    )
    episode_id = memory.store_episode(
        "Legacy alias fact", metadata=metadata(tenant="acme-legacy"),
        bypass_filter=True,
    )
    assert episode_id
    assert memory.search_episodes("Legacy alias", n=5)[0].episode_id == episode_id


def test_review_classifies_legacy_episode_and_persists_audit(tmp_path):
    unguarded = ProjectMemory(base_dir=tmp_path, project_id="p")
    episode_id = unguarded.store_episode("Legacy Atlas region west", bypass_filter=True)
    unguarded.close()
    guarded = ProjectMemory(base_dir=tmp_path, project_id="p", trust_policy=policy())
    assert guarded.search_episodes("Atlas region", n=5) == []
    result = guarded.review_episode_trust(
        episode_id, trust="verified", tenant="acme", source="operator",
        writer="admin", reviewer="security-reviewer",
    )
    assert result["action"] == "accept"
    assert guarded.search_episodes("Atlas region", n=5)[0].episode_id == episode_id
    guarded.close()
    reopened = ProjectMemory(base_dir=tmp_path, project_id="p", trust_policy=policy())
    reviewed = reopened.search_episodes("Atlas region", n=5)[0]
    assert reviewed.metadata["trust_reviewer"] == "security-reviewer"
    assert len(reviewed.metadata["trust_review_history"]) == 1


def test_quarantine_release_requires_valid_metadata_and_explicit_release(tmp_path):
    memory = ProjectMemory(
        base_dir=tmp_path, project_id="p",
        trust_policy=policy(ingestion_violation="quarantine"),
    )
    episode_id = memory.store_episode(
        "Reviewed Atlas fact", metadata=metadata(trust="low"), bypass_filter=True,
    )
    rejected = memory.review_episode_trust(
        episode_id, trust="verified", tenant="wrong", source="operator",
        writer="admin", reviewer="reviewer", release_quarantine=True,
    )
    assert rejected["action"] == "reject"
    assert memory.search_episodes("Reviewed Atlas", n=5) == []
    accepted = memory.review_episode_trust(
        episode_id, trust="verified", tenant="acme", source="operator",
        writer="admin", reviewer="reviewer", release_quarantine=True,
    )
    assert accepted == {
        "episode_id": episode_id, "action": "accept", "reasons": [],
        "released": True, "reviewer": "reviewer",
    }
    assert memory.search_episodes("Reviewed Atlas", n=5)[0].episode_id == episode_id

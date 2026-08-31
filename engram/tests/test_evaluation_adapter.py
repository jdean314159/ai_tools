from __future__ import annotations

from engram import ProjectMemory, observation_from_engram
from llm_harness_core import MemoryCaseSpec, evaluate_memory_case


def test_engram_adapter_attributes_real_retrieval_and_composition(tmp_path):
    memory = ProjectMemory(base_dir=tmp_path, project_id="eval", session_id="probe")
    episode_id = memory.store_temporal_episode(
        "Atlas region is eu-central-1.",
        topic_key="atlas::region",
        action="set",
        metadata={"evidence_id": "current"},
        importance=1.0,
        bypass_filter=True,
    )
    retrieved = memory.search_episodes("Atlas current region", n=5)
    prompt_result = memory.build_prompt(
        "What is Atlas's current region?",
        query="Atlas current region",
        reserve_output_tokens=32,
        return_trace=True,
    )
    observation = observation_from_engram(
        stored_count=1,
        retrieved_items=retrieved,
        prompt_result=prompt_result,
        observed_output={"value": "eu-central-1", "evidence_id": "current"},
    )
    evaluation = evaluate_memory_case(
        MemoryCaseSpec(
            case_id="atlas",
            expected_storage_count=1,
            required_evidence_ids=("current",),
            expected_output={"value": "eu-central-1", "evidence_id": "current"},
        ),
        observation,
    )

    assert episode_id
    assert observation.retrieved_evidence_ids == ("current",)
    assert observation.prompt_evidence_ids == ("current",)
    assert observation.diagnostics["budget"]["memory_included_count"] >= 1
    assert evaluation.end_to_end_passed is True


def test_engram_adapter_exposes_budget_starvation_as_composition_failure(tmp_path):
    memory = ProjectMemory(base_dir=tmp_path, project_id="starved", session_id="probe")
    memory.store_episode(
        "Relevant evidence " + "word " * 30,
        metadata={"evidence_id": "needed"},
        importance=1.0,
        bypass_filter=True,
    )
    retrieved = memory.search_episodes("Relevant evidence", n=5)
    prompt_result = memory.build_prompt(
        "Question with a deliberately constrained prompt budget",
        query="Relevant evidence",
        max_prompt_tokens=12,
        reserve_output_tokens=6,
        return_trace=True,
    )
    observation = observation_from_engram(
        stored_count=1,
        retrieved_items=retrieved,
        prompt_result=prompt_result,
        observed_output={"value": "UNKNOWN"},
    )
    evaluation = evaluate_memory_case(
        MemoryCaseSpec(
            case_id="starved",
            expected_storage_count=1,
            required_evidence_ids=("needed",),
            expected_output={"value": "answer"},
        ),
        observation,
    )

    assert observation.diagnostics["budget"]["memory_starved"] is True
    assert evaluation.retrieval_passed is True
    assert evaluation.composition_passed is False
    assert evaluation.primary_failure_stage == "composition"

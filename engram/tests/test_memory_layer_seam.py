from __future__ import annotations

import logging
from typing import Any

import pytest

from engram import (
    MemoryObservation,
    ProjectMemory,
    PromptHint,
    RecallContribution,
    RecallQuery,
)


class RecordingLayer:
    name = "recording"

    def __init__(self) -> None:
        self.observations: list[MemoryObservation] = []
        self.recall_queries: list[RecallQuery] = []
        self.prompt_queries: list[RecallQuery] = []
        self.boost_candidate_id: str | None = None
        self.boost_value = 10.0
        self.persist_calls = 0
        self.close_calls = 0

    def observe(self, observation: MemoryObservation) -> None:
        self.observations.append(observation)

    def contribute_to_recall(self, query: RecallQuery) -> RecallContribution | None:
        self.recall_queries.append(query)
        if self.boost_candidate_id is None:
            return None
        return RecallContribution(affinity={self.boost_candidate_id: self.boost_value})

    def contribute_to_prompt(self, query: RecallQuery) -> PromptHint | None:
        self.prompt_queries.append(query)
        return PromptHint(
            text="The neural extension reports strong familiarity with this topic.",
            metadata={"novelty": 0.1},
        )

    def warmup(self, history: list[MemoryObservation]) -> None:
        del history

    def persist(self) -> None:
        self.persist_calls += 1

    def close(self) -> None:
        self.close_calls += 1


class FailingLayer:
    name = "failing"

    def _fail(self) -> None:
        raise RuntimeError("deliberate extension failure")

    def observe(self, observation: MemoryObservation) -> None:
        del observation
        self._fail()

    def contribute_to_recall(self, query: RecallQuery) -> RecallContribution | None:
        del query
        self._fail()

    def contribute_to_prompt(self, query: RecallQuery) -> PromptHint | None:
        del query
        self._fail()

    def warmup(self, history: list[MemoryObservation]) -> None:
        del history
        self._fail()

    def persist(self) -> None:
        self._fail()

    def close(self) -> None:
        self._fail()


def _seed_memory(memory: ProjectMemory) -> tuple[str, str]:
    first = memory.store_episode(
        "The architecture uses a stable shared interoperability core.",
        importance=0.95,
        bypass_filter=True,
    )
    second = memory.store_episode(
        "The release checklist includes documentation validation.",
        importance=0.65,
        bypass_filter=True,
    )
    return first, second


def _result_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt": result["prompt"],
        "prompt_tokens": result["prompt_tokens"],
        "memory_tokens": result["memory_tokens"],
        "compressed": result["compressed"],
    }


def test_no_registered_layers_preserve_core_flow() -> None:
    baseline = ProjectMemory(
        session_id="s1",
        auto_ingest_turns=False,
        auto_pair_assistant=False,
    )
    comparison = ProjectMemory(
        session_id="s1",
        auto_ingest_turns=False,
        auto_pair_assistant=False,
    )

    for memory in (baseline, comparison):
        memory.add_turn("user", "Keep the architecture explicit.", session_id="s1")
        _seed_memory(memory)

    baseline_search = [
        (item.text, item.importance) for item in baseline.search_episodes("architecture", n=5)
    ]
    comparison_search = [
        (item.text, item.importance) for item in comparison.search_episodes("architecture", n=5)
    ]

    assert comparison_search == baseline_search
    baseline_prompt = baseline.build_prompt("Explain the architecture.")
    comparison_prompt = comparison.build_prompt("Explain the architecture.")
    assert _result_snapshot(comparison_prompt) == _result_snapshot(baseline_prompt)
    assert "advisory_hints" not in baseline_prompt
    assert "Memory Layer Hints" not in baseline_prompt["prompt"]


def test_recording_layer_observes_turns_and_episodes() -> None:
    memory = ProjectMemory(
        session_id="s1",
        auto_ingest_turns=False,
        auto_pair_assistant=False,
    )
    layer = RecordingLayer()
    memory.register_layer(layer)

    memory.add_turn("user", "A working-memory observation.", session_id="s1")
    episode_id = memory.store_episode(
        "An explicit episodic observation.",
        metadata={"role": "assistant", "session_id": "s1"},
        importance=0.9,
        bypass_filter=True,
    )

    assert episode_id
    assert [(item.role, item.text) for item in layer.observations] == [
        ("user", "A working-memory observation."),
        ("assistant", "An explicit episodic observation."),
    ]
    assert layer.observations[1].metadata["episode_id"] == episode_id


def test_recall_contribution_can_reorder_existing_candidates() -> None:
    memory = ProjectMemory(session_id="s1")
    layer = RecordingLayer()
    memory.register_layer(layer)
    first_id, second_id = _seed_memory(memory)

    baseline = memory.search_episodes("", n=5)
    assert baseline[0].text.startswith("The architecture")

    layer.boost_candidate_id = second_id
    boosted = memory.search_episodes("", n=5)

    assert first_id != second_id
    assert boosted[0].text.startswith("The release checklist")
    assert layer.recall_queries
    assert second_id in layer.recall_queries[-1].metadata["candidate_ids"]


def test_recall_contribution_is_scaled_by_original_score_spread() -> None:
    memory = ProjectMemory(session_id="s1")
    layer = RecordingLayer()
    layer.boost_candidate_id = "second"
    layer.boost_value = 0.3
    memory.register_layer(layer)
    rows = [
        {"id": "first", "final_score": 0.04, "importance": 0.5},
        {"id": "second", "final_score": 0.02, "importance": 0.5},
    ]

    ranked = memory._apply_recall_contributions(rows, query="test")

    second = next(row for row in ranked if row["id"] == "second")
    assert second["final_score"] == pytest.approx(0.02 + 0.3 * 0.02)
    assert ranked[0]["id"] == "first"


def test_recall_contribution_is_noop_for_tied_scores() -> None:
    memory = ProjectMemory(session_id="s1")
    layer = RecordingLayer()
    layer.boost_candidate_id = "second"
    memory.register_layer(layer)
    rows = [
        {"id": "first", "final_score": 0.02, "importance": 0.5},
        {"id": "second", "final_score": 0.02, "importance": 0.5},
    ]

    ranked = memory._apply_recall_contributions(rows, query="test")

    assert [row["final_score"] for row in ranked] == [0.02, 0.02]


def test_prompt_contribution_is_budgeted_and_visible() -> None:
    memory = ProjectMemory(session_id="s1")
    layer = RecordingLayer()
    memory.register_layer(layer)

    result = memory.build_prompt("What feels familiar?", return_trace=True)

    assert "## Memory Layer Hints" in result["prompt"]
    assert "strong familiarity" in result["prompt"]
    assert result["memory_tokens"] > 0
    assert result["advisory_hints"][0].metadata["novelty"] == 0.1
    assert layer.prompt_queries[-1].query == "What feels familiar?"
    assert any(section.origin == "memory_layer" for section in result["trace"].sections)


def test_close_persists_and_closes_layers_once() -> None:
    memory = ProjectMemory(session_id="s1")
    layer = RecordingLayer()
    memory.register_layer(layer)

    memory.close()
    memory.close()

    assert layer.persist_calls == 1
    assert layer.close_calls == 1


def test_failing_layer_never_breaks_core_flows(caplog) -> None:
    baseline = ProjectMemory(
        session_id="s1",
        auto_ingest_turns=False,
        auto_pair_assistant=False,
    )
    memory = ProjectMemory(
        session_id="s1",
        auto_ingest_turns=False,
        auto_pair_assistant=False,
    )
    memory.register_layer(FailingLayer())

    with caplog.at_level(logging.WARNING):
        for item in (baseline, memory):
            item.add_turn("user", "Keep core behavior stable.", session_id="s1")
            _seed_memory(item)

        actual_search = [
            (item.text, item.importance) for item in memory.search_episodes("architecture", n=5)
        ]
        expected_search = [
            (item.text, item.importance) for item in baseline.search_episodes("architecture", n=5)
        ]
        actual_prompt = _result_snapshot(memory.build_prompt("Explain the architecture."))
        expected_prompt = _result_snapshot(baseline.build_prompt("Explain the architecture."))
        memory.close()

    assert actual_search == expected_search
    assert actual_prompt == expected_prompt
    assert "memory layer failing observe failed" in caplog.text
    assert "memory layer failing recall contribution failed" in caplog.text
    assert "memory layer failing prompt contribution failed" in caplog.text
    assert "memory layer failing persist failed" in caplog.text
    assert "memory layer failing close failed" in caplog.text

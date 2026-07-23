from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from agent_lib.eval.navigation_claims import EvidenceRef
from agent_lib.eval.verifiable_navigation import (
    PythonRelationOracle,
    RelationCanonicalizer,
    RelationClaim,
    VerifiableTask,
    VerifiableNavigationError,
    build_task_admission_manifest,
    build_pair_manifest,
    classify_task_difficulty,
    load_verifiable_task_set,
    relation_claims_shape_error,
    score_verifiable_claims,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "nav_verifiable"


def _write_task_set(path: Path) -> None:
    source = FIXTURE_ROOT / "sample.py"
    payload = {
        "schema_version": 1,
        "track": "NAV-VERIFIABLE-00",
        "sources": {
            "sample.py": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
        "tasks": [
            {
                "task_id": "definition",
                "kind": "definition",
                "question": "Locate Store.add.",
                "path": "sample.py",
                "symbol": "Store.add",
                "goal_requirements": [
                    {
                        "goal_id": "locate_definition",
                        "requirement": "Locate the Store.add definition.",
                    }
                ],
            },
            {
                "task_id": "direct_callers",
                "kind": "direct_callers",
                "question": "Find direct callers of Pipeline._store_add.",
                "path": "sample.py",
                "symbol": "Pipeline._store_add",
                "goal_requirements": [
                    {
                        "goal_id": "find_callers",
                        "requirement": "Find direct callers of Pipeline._store_add.",
                    }
                ],
            },
            {
                "task_id": "call_path",
                "kind": "call_path",
                "question": "Trace Pipeline.ingest to Pipeline._store_add.",
                "path": "sample.py",
                "symbol": "Pipeline.ingest",
                "endpoint": "Pipeline._store_add",
                "goal_requirements": [
                    {
                        "goal_id": "trace_path",
                        "requirement": "Trace the specified call path.",
                    }
                ],
            },
            {
                "task_id": "mutation_target",
                "kind": "mutation_target",
                "question": "Identify the call at Pipeline._store_add line 14.",
                "path": "sample.py",
                "symbol": "Pipeline._store_add",
                "line": 14,
                "goal_requirements": [
                    {
                        "goal_id": "identify_target",
                        "requirement": "Identify the callable at the named site.",
                    }
                ],
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_task_set_loads_and_oracle_resolves_all_shapes(tmp_path) -> None:
    tasks = load_verifiable_task_set(
        FIXTURE_ROOT / "tasks.json", source_root=FIXTURE_ROOT
    )
    oracle = PythonRelationOracle(FIXTURE_ROOT)

    definition = oracle.expected(tasks[0])
    callers = oracle.expected(tasks[1])
    path = oracle.expected(tasks[2])
    mutation = oracle.expected(tasks[3])

    assert definition[0].symbol == "sample.Store.add"
    assert callers[0].symbol == "sample.Pipeline._prepare"
    assert callers[0].target == "sample.Pipeline._store_add"
    assert path[0].path_symbols == (
        "sample.Pipeline.ingest",
        "sample.Pipeline._prepare",
        "sample.Pipeline._store_add",
    )
    assert mutation[0].target == "self.store.add"


def test_exact_relation_scoring_rejects_indirect_call_as_direct(tmp_path) -> None:
    fixture = tmp_path / "tasks.json"
    _write_task_set(fixture)
    task = load_verifiable_task_set(fixture, source_root=FIXTURE_ROOT)[1]
    oracle = PythonRelationOracle(FIXTURE_ROOT)
    observed = {"sample.py": set(range(1, 15))}
    correct = RelationClaim(
        kind="call_edge",
        path="sample.py",
        symbol="sample.Pipeline._prepare",
        target="sample.Pipeline._store_add",
        evidence=(EvidenceRef("sample.py", 11, 11),),
    )
    indirect = RelationClaim(
        kind="call_edge",
        path="sample.py",
        symbol="sample.Pipeline.ingest",
        target="sample.Pipeline._store_add",
        evidence=(EvidenceRef("sample.py", 8, 8),),
    )

    accepted = score_verifiable_claims(
        task, [correct], oracle=oracle, observed_lines=observed
    )
    rejected = score_verifiable_claims(
        task, [indirect], oracle=oracle, observed_lines=observed
    )

    assert accepted.correct is True
    assert rejected.correct is False
    assert rejected.unsupported_claims == (indirect.as_dict(),)


def test_two_sided_canonicalization_accepts_task_visible_symbols_and_calls(
    tmp_path,
) -> None:
    fixture = tmp_path / "tasks.json"
    _write_task_set(fixture)
    tasks = load_verifiable_task_set(fixture, source_root=FIXTURE_ROOT)
    oracle = PythonRelationOracle(FIXTURE_ROOT)
    observed = {"sample.py": set(range(1, 15))}
    caller_score = score_verifiable_claims(
        tasks[1],
        [
            RelationClaim(
                kind="call_edge",
                path="sample.py",
                symbol="Pipeline._prepare",
                target="Pipeline._store_add",
                evidence=(EvidenceRef("sample.py", 11, 11),),
            )
        ],
        oracle=oracle,
        observed_lines=observed,
    )
    mutation_score = score_verifiable_claims(
        tasks[3],
        [
            RelationClaim(
                kind="mutation_target",
                path="sample.py",
                symbol="Pipeline._store_add",
                target="self.store.add(value)",
                evidence=(EvidenceRef("sample.py", 14, 14),),
            )
        ],
        oracle=oracle,
        observed_lines=observed,
    )

    assert caller_score.correct is True
    assert caller_score.normalized_claims[0]["symbol"] == "Pipeline._prepare"
    assert mutation_score.correct is True
    assert mutation_score.normalized_claims[0]["target"] == "self.store.add"


def test_path_scoring_requires_every_edge_line_and_reports_extra_lines(
    tmp_path,
) -> None:
    fixture = tmp_path / "tasks.json"
    _write_task_set(fixture)
    task = load_verifiable_task_set(fixture, source_root=FIXTURE_ROOT)[2]
    oracle = PythonRelationOracle(FIXTURE_ROOT)
    observed = {"sample.py": set(range(1, 15))}
    missing_edge = RelationClaim(
        kind="call_path",
        path="sample.py",
        symbol="Pipeline.ingest",
        target="Pipeline._store_add",
        path_symbols=(
            "Pipeline.ingest",
            "Pipeline._prepare",
            "Pipeline._store_add",
        ),
        evidence=(EvidenceRef("sample.py", 8, 8),),
    )
    broad = RelationClaim(
        kind="call_path",
        path="sample.py",
        symbol="Pipeline.ingest",
        target="Pipeline._store_add",
        path_symbols=missing_edge.path_symbols,
        evidence=(EvidenceRef("sample.py", 7, 14),),
    )
    exact = RelationClaim(
        kind="call_path",
        path="sample.py",
        symbol="Pipeline.ingest",
        target="Pipeline._store_add",
        path_symbols=missing_edge.path_symbols,
        evidence=(
            EvidenceRef("sample.py", 8, 8),
            EvidenceRef("sample.py", 11, 11),
        ),
    )

    missing_score = score_verifiable_claims(
        task, [missing_edge], oracle=oracle, observed_lines=observed
    )
    broad_score = score_verifiable_claims(
        task, [broad], oracle=oracle, observed_lines=observed
    )
    exact_score = score_verifiable_claims(
        task, [exact], oracle=oracle, observed_lines=observed
    )

    assert missing_score.correct is False
    assert missing_score.relation_correct is True
    assert missing_score.evidence_complete is False
    assert missing_score.unsupported_claims == ()
    assert missing_score.incomplete_evidence_claims[0]["missing_lines"] == [11]
    assert broad_score.correct is False
    assert broad_score.relation_correct is True
    assert broad_score.evidence_complete is True
    assert broad_score.evidence_precise is False
    assert broad_score.imprecise_claims[0]["extra_lines"] == [7, 9, 10, 12, 13, 14]
    assert exact_score.correct is True
    assert exact_score.relation_correct is True
    assert exact_score.evidence_complete is True
    assert exact_score.evidence_precise is True


def test_claim_requires_observed_relation_evidence(tmp_path) -> None:
    fixture = tmp_path / "tasks.json"
    _write_task_set(fixture)
    task = load_verifiable_task_set(fixture, source_root=FIXTURE_ROOT)[0]
    claim = RelationClaim(
        kind="definition",
        path="sample.py",
        symbol="sample.Store.add",
        evidence=(EvidenceRef("sample.py", 2, 2),),
    )

    score = score_verifiable_claims(
        task,
        [claim],
        oracle=PythonRelationOracle(FIXTURE_ROOT),
        observed_lines={"sample.py": {1}},
    )

    assert score.correct is False
    assert score.errors == ("claim 1 references unobserved evidence",)


def test_fixture_hash_and_dynamic_calls_fail_closed(tmp_path) -> None:
    fixture = tmp_path / "tasks.json"
    _write_task_set(fixture)
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    payload["sources"]["sample.py"] = "0" * 64
    fixture.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(VerifiableNavigationError, match="source hash mismatch"):
        load_verifiable_task_set(fixture, source_root=FIXTURE_ROOT)

    dynamic = tmp_path / "dynamic"
    dynamic.mkdir()
    (dynamic / "sample.py").write_text(
        "def run(factory):\n    return factory()()\n",
        encoding="utf-8",
    )
    with pytest.raises(VerifiableNavigationError, match="dynamic call"):
        PythonRelationOracle(dynamic)


def test_task_set_rejects_unpinned_python_sources(tmp_path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "sample.py").write_text(
        (FIXTURE_ROOT / "sample.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (source_root / "untracked.py").write_text(
        "def hidden():\n    return None\n", encoding="utf-8"
    )
    fixture = tmp_path / "tasks.json"
    _write_task_set(fixture)

    with pytest.raises(VerifiableNavigationError, match="exactly match"):
        load_verifiable_task_set(fixture, source_root=source_root)


def test_task_set_rejects_empty_direct_caller_answer(tmp_path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = source_root / "sample.py"
    source.write_text("def target():\n    return None\n", encoding="utf-8")
    fixture = tmp_path / "tasks.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "track": "NAV-VERIFIABLE-00",
                "sources": {
                    "sample.py": hashlib.sha256(source.read_bytes()).hexdigest()
                },
                "tasks": [
                    {
                        "task_id": "empty",
                        "kind": "direct_callers",
                        "question": "Find callers.",
                        "path": "sample.py",
                        "symbol": "target",
                        "goal_requirements": [
                            {
                                "goal_id": "find_callers",
                                "requirement": "Find direct callers.",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(VerifiableNavigationError, match="no exact expected"):
        load_verifiable_task_set(fixture, source_root=source_root)


def test_pair_manifest_enforces_identical_configuration_and_modes(tmp_path) -> None:
    fixture = tmp_path / "tasks.json"
    _write_task_set(fixture)
    task = load_verifiable_task_set(fixture, source_root=FIXTURE_ROOT)[0]
    autonomous = {
        "model": "model",
        "seed": 3,
        "budget": 20_000,
        "structured_navigation": False,
        "output_dir": "autonomous",
    }
    structured = {
        **autonomous,
        "structured_navigation": True,
        "output_dir": "structured",
    }

    manifest = build_pair_manifest(
        pair_id="pair-01",
        task=task,
        autonomous_config=autonomous,
        structured_config=structured,
        run_order=("autonomous", "structured"),
    )

    assert manifest["task_id"] == "definition"
    assert manifest["shared_config"]["seed"] == 3
    with pytest.raises(VerifiableNavigationError, match="must share"):
        build_pair_manifest(
            pair_id="pair-02",
            task=task,
            autonomous_config=autonomous,
            structured_config={**structured, "seed": 4},
            run_order=("structured", "autonomous"),
        )


def test_relation_claim_contract_rejects_invalid_paths() -> None:
    assert (
        relation_claims_shape_error(
            [
                {
                    "kind": "call_path",
                    "path": "sample.py",
                    "symbol": "sample.Pipeline.ingest",
                    "target": "sample.Pipeline._store_add",
                    "path_symbols": [
                        "sample.Pipeline.ingest",
                        "sample.Pipeline._prepare",
                    ],
                    "evidence": [
                        {
                            "path": "sample.py",
                            "start_line": 8,
                            "end_line": 11,
                        }
                    ],
                }
            ]
        )
        == "relation claim 1 has invalid path_symbols"
    )


def test_oracle_rejects_aliases_instead_of_guessing_edges(tmp_path) -> None:
    (tmp_path / "sample.py").write_text(
        "def target():\n"
        "    return None\n"
        "\n"
        "alias = target\n"
        "\n"
        "def caller():\n"
        "    alias()\n",
        encoding="utf-8",
    )

    with pytest.raises(VerifiableNavigationError, match="assignment alias"):
        PythonRelationOracle(tmp_path)


def test_same_named_methods_require_a_qualified_symbol(tmp_path) -> None:
    (tmp_path / "sample.py").write_text(
        "class Left:\n"
        "    def run(self):\n"
        "        return None\n"
        "\n"
        "class Right:\n"
        "    def run(self):\n"
        "        return None\n",
        encoding="utf-8",
    )
    oracle = PythonRelationOracle(tmp_path)

    with pytest.raises(VerifiableNavigationError, match="resolve exactly once"):
        oracle.definition(path="sample.py", symbol="run")

    assert (
        oracle.definition(path="sample.py", symbol="Left.run").symbol
        == "sample.Left.run"
    )


def test_canonicalizer_rejects_fixture_wide_symbol_collisions(tmp_path) -> None:
    (tmp_path / "left.py").write_text(
        "class Runner:\n    def run(self):\n        return None\n",
        encoding="utf-8",
    )
    (tmp_path / "right.py").write_text(
        "class Runner:\n    def run(self):\n        return None\n",
        encoding="utf-8",
    )

    with pytest.raises(VerifiableNavigationError, match="canonical symbol collision"):
        RelationCanonicalizer(PythonRelationOracle(tmp_path))


def test_admission_manifest_freezes_structural_difficulty_before_runs(
    tmp_path,
) -> None:
    (tmp_path / "main.py").write_text(
        "class Pipeline:\n"
        "    def start(self):\n"
        "        return self._one()\n"
        "    def _one(self):\n"
        "        return self._two()\n"
        "    def _two(self):\n"
        "        return self.finish()\n"
        "    def finish(self):\n"
        "        return None\n",
        encoding="utf-8",
    )
    for index in range(4):
        (tmp_path / f"decoy_{index}.py").write_text(
            f"class Decoy{index}:\n"
            "    def finish(self):\n"
            "        return None\n",
            encoding="utf-8",
        )
    task = VerifiableTask(
        task_id="exploratory_path",
        kind="call_path",
        question="Trace Pipeline.start to Pipeline.finish.",
        path="main.py",
        symbol="Pipeline.start",
        endpoint="Pipeline.finish",
        goal_requirements=(("trace", "Trace the specified path."),),
    )
    oracle = PythonRelationOracle(tmp_path)

    difficulty = classify_task_difficulty(task, oracle=oracle)
    manifest = build_task_admission_manifest([task], oracle=oracle)

    assert difficulty.hop_count == 3
    assert difficulty.candidate_file_count == 5
    assert difficulty.decoy_count == 4
    assert difficulty.tier == "exploratory"
    assert manifest["tasks"][0]["difficulty"] == difficulty.as_dict()
    assert len(manifest["admission_manifest_sha256"]) == 64


def test_existing_direct_caller_fixture_is_predeclared_local() -> None:
    task = load_verifiable_task_set(
        FIXTURE_ROOT / "tasks.json", source_root=FIXTURE_ROOT
    )[1]
    oracle = PythonRelationOracle(FIXTURE_ROOT)

    difficulty = classify_task_difficulty(task, oracle=oracle)

    assert difficulty.tier == "local"
    assert difficulty.hop_count == 1
    assert difficulty.candidate_file_count == 1
    assert difficulty.decoy_count == 0


def test_nested_function_calls_are_not_attributed_to_parent(tmp_path) -> None:
    (tmp_path / "sample.py").write_text(
        "def target():\n"
        "    return None\n"
        "\n"
        "def outer():\n"
        "    def inner():\n"
        "        target()\n"
        "    return inner\n",
        encoding="utf-8",
    )
    oracle = PythonRelationOracle(tmp_path)

    callers = oracle.direct_callers(path="sample.py", symbol="target")

    assert tuple(item.symbol for item in callers) == ("sample.outer.inner",)

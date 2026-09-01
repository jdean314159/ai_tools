from __future__ import annotations

from agent_lib.eval.navigation_claims import (
    EvidenceRef,
    NavigationClaim,
    validate_navigation_claims,
)
from agent_lib.eval.navigation_ground_truth import GroundTruthRegion as GroundTruthRegionOwner
from agent_lib.eval.navigation_contracts import NavigationConfigurationError as ErrorOwner
from agent_lib.eval.navigation_model_transport import LlamaServerClient as LlamaServerClientOwner
from agent_lib.eval.navigation_planner import (
    BudgetedNavigationPlanner as PlannerOwner,
    NavigationBudget as BudgetOwner,
    NavigationRunHook as RunHookOwner,
    PlannerUsage as PlannerUsageOwner,
)
from agent_lib.eval.navigation_context import NoWriteContextBuilder as ContextBuilderOwner
from agent_lib.eval.navigation_artifacts import (
    build_environment_manifest as EnvironmentManifestOwner,
    render_run_record as RunRecordOwner,
    tree_content_digest as TreeDigestOwner,
)
from agent_lib.eval.navigation_scoring import score_navigation_run as ScoringOwner
from agent_lib.eval.navigation_workspace import NavigationWorkspace as WorkspaceOwner
from agent_lib.eval.repo_navigation import (
    GroundTruthRegion,
    BudgetedNavigationPlanner,
    build_environment_manifest,
    LlamaServerClient,
    NavigationBudget,
    NavigationConfigurationError,
    NavigationRunHook,
    NavigationWorkspace,
    NoWriteContextBuilder,
    PlannerUsage,
    render_run_record,
    score_navigation_run,
    tree_content_digest,
)


def test_ground_truth_region_compatibility_export_preserves_identity() -> None:
    assert GroundTruthRegion is GroundTruthRegionOwner
    assert NavigationConfigurationError is ErrorOwner
    assert LlamaServerClient is LlamaServerClientOwner
    assert NavigationWorkspace is WorkspaceOwner
    assert NoWriteContextBuilder is ContextBuilderOwner
    assert BudgetedNavigationPlanner is PlannerOwner
    assert NavigationBudget is BudgetOwner
    assert NavigationRunHook is RunHookOwner
    assert PlannerUsage is PlannerUsageOwner
    assert build_environment_manifest is EnvironmentManifestOwner
    assert render_run_record is RunRecordOwner
    assert score_navigation_run is ScoringOwner
    assert tree_content_digest is TreeDigestOwner


def _telemetry() -> list[dict]:
    return [
        {
            "success": True,
            "evidence": [{"path": "pipeline.py", "lines": list(range(281, 314))}],
        }
    ]


def _region() -> GroundTruthRegion:
    return GroundTruthRegion(
        id="GT-01",
        path="pipeline.py",
        start_line=310,
        end_line=313,
        classification="pipeline mutation",
        required_answer_terms=("ingest", "delete_by_source"),
        symbol="RAGPipeline.ingest",
    )


def test_valid_claim_requires_local_terms_and_observed_evidence() -> None:
    claim = NavigationClaim(
        path="pipeline.py",
        symbol="RAGPipeline.ingest",
        operation="self._store.delete_by_source",
        classification="pipeline mutation",
        evidence=(EvidenceRef("pipeline.py", 310, 313),),
    )

    result = validate_navigation_claims([claim], telemetry_calls=_telemetry(), regions=[_region()])

    assert result.valid is True
    assert result.matched_region_ids == ("GT-01",)


def test_fabricated_symbol_is_an_unsupported_claim() -> None:
    claim = NavigationClaim(
        path="pipeline.py",
        symbol="RAGPipeline.ingest_file",
        operation="self._store.delete_by_source",
        classification="pipeline mutation",
        evidence=(EvidenceRef("pipeline.py", 310, 313),),
    )

    result = validate_navigation_claims([claim], telemetry_calls=_telemetry(), regions=[_region()])

    assert result.valid is False
    assert result.matched_region_ids == ()
    assert result.unsupported_claims[0]["symbol"] == "RAGPipeline.ingest_file"


def test_python_symbol_must_enclose_cited_evidence(tmp_path) -> None:
    (tmp_path / "pipeline.py").write_text(
        "\n" * 279
        + "class RAGPipeline:\n"
        + "    def ingest(self):\n"
        + "        self._store.delete_by_source()\n"
        + "\n" * 30,
        encoding="utf-8",
    )
    telemetry = [
        {
            "success": True,
            "evidence": [{"path": "pipeline.py", "lines": [281, 282]}],
        }
    ]
    region = GroundTruthRegion(
        id="GT-01",
        path="pipeline.py",
        start_line=281,
        end_line=282,
        classification="pipeline mutation",
        required_answer_terms=("ingest", "delete_by_source"),
        symbol="RAGPipeline.ingest",
    )

    valid = validate_navigation_claims(
        [
            NavigationClaim(
                path="pipeline.py",
                symbol="RAGPipeline.ingest",
                operation="self._store.delete_by_source",
                classification="pipeline mutation",
                evidence=(EvidenceRef("pipeline.py", 281, 282),),
            )
        ],
        telemetry_calls=telemetry,
        regions=[region],
        source_root=tmp_path,
    )
    invented = validate_navigation_claims(
        [
            NavigationClaim(
                path="pipeline.py",
                symbol="RAGPipeline.ingest_file",
                operation="self._store.delete_by_source",
                classification="pipeline mutation",
                evidence=(EvidenceRef("pipeline.py", 281, 282),),
            )
        ],
        telemetry_calls=telemetry,
        regions=[region],
        source_root=tmp_path,
    )

    assert valid.valid is True
    assert invented.errors == (
        "claim 1 symbol 'RAGPipeline.ingest_file' does not enclose its cited evidence",
    )


def test_symbol_grounding_does_not_claim_to_validate_call_relations(tmp_path) -> None:
    (tmp_path / "pipeline.py").write_text(
        "class RAGPipeline:\n    def ingest(self):\n        self._embed_and_store()\n",
        encoding="utf-8",
    )
    claim = NavigationClaim(
        path="pipeline.py",
        symbol="RAGPipeline.ingest",
        operation="self._embed_and_store",
        classification="claimed direct mutation",
        evidence=(EvidenceRef("pipeline.py", 2, 3),),
    )
    region = GroundTruthRegion(
        id="GT-01",
        path="pipeline.py",
        start_line=2,
        end_line=3,
        classification="claimed direct mutation",
        required_answer_terms=("ingest", "_embed_and_store"),
        symbol="RAGPipeline.ingest",
    )

    result = validate_navigation_claims(
        [claim],
        telemetry_calls=[
            {
                "success": True,
                "evidence": [{"path": "pipeline.py", "lines": [2, 3]}],
            }
        ],
        regions=[region],
        source_root=tmp_path,
    )

    assert result.valid is True


def test_unobserved_line_reference_is_rejected() -> None:
    claim = NavigationClaim(
        path="pipeline.py",
        symbol="RAGPipeline.ingest",
        operation="self._store.delete_by_source",
        classification="pipeline mutation",
        evidence=(EvidenceRef("pipeline.py", 310, 314),),
    )

    result = validate_navigation_claims([claim], telemetry_calls=_telemetry(), regions=[_region()])

    assert result.valid is False
    assert result.errors == ("claim 1 references unobserved evidence",)

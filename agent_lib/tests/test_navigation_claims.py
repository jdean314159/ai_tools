from __future__ import annotations

from agent_lib.eval.navigation_claims import (
    EvidenceRef,
    NavigationClaim,
    validate_navigation_claims,
)
from agent_lib.eval.repo_navigation import GroundTruthRegion


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

    result = validate_navigation_claims(
        [claim], telemetry_calls=_telemetry(), regions=[_region()]
    )

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

    result = validate_navigation_claims(
        [claim], telemetry_calls=_telemetry(), regions=[_region()]
    )

    assert result.valid is False
    assert result.matched_region_ids == ()
    assert result.unsupported_claims[0]["symbol"] == "RAGPipeline.ingest_file"


def test_unobserved_line_reference_is_rejected() -> None:
    claim = NavigationClaim(
        path="pipeline.py",
        symbol="RAGPipeline.ingest",
        operation="self._store.delete_by_source",
        classification="pipeline mutation",
        evidence=(EvidenceRef("pipeline.py", 310, 314),),
    )

    result = validate_navigation_claims(
        [claim], telemetry_calls=_telemetry(), regions=[_region()]
    )

    assert result.valid is False
    assert result.errors == ("claim 1 references unobserved evidence",)

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("validate_decision_history.py")
SPEC = importlib.util.spec_from_file_location("validate_decision_history", SCRIPT_PATH)
assert SPEC is not None
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def record(**overrides: object) -> dict:
    payload = {
        "id": "cache-adapter",
        "application_scope": "response-caching",
        "resolution_status": "qualified",
        "mechanism_status": "operational",
        "mechanism_evidence": ["docs/evidence.md#result"],
        "earlier_support": {
            "basis": "The mechanism had a plausible design.",
            "evidence": ["docs/evidence.md#support"],
        },
        "resolution_evidence": ["docs/evidence.md#result"],
        "superseded_by": None,
        "current_guidance": "The mechanism remains default-off.",
    }
    payload.update(overrides)
    return payload


def write_adr(path: Path, hypothesis: dict) -> None:
    import yaml

    metadata = {
        "decision_history_version": 1,
        "hypotheses": [hypothesis],
    }
    path.write_text(
        "---\n"
        + yaml.safe_dump(metadata, sort_keys=False)
        + "---\n\n# ADR-999: Test\n",
        encoding="utf-8",
    )


def test_operational_requires_mechanism_evidence() -> None:
    payload = record(mechanism_evidence=[])

    try:
        validator.HypothesisRecord.model_validate(payload)
    except Exception as exc:
        assert "operational mechanisms require mechanism_evidence" in str(exc)
    else:
        raise AssertionError("operational mechanism without evidence was accepted")


def test_not_demonstrated_requires_empty_mechanism_evidence() -> None:
    payload = record(mechanism_status="not_demonstrated")

    try:
        validator.HypothesisRecord.model_validate(payload)
    except Exception as exc:
        assert "not_demonstrated mechanisms require empty" in str(exc)
    else:
        raise AssertionError("not_demonstrated mechanism with evidence was accepted")


def test_heading_slugs_include_duplicate_suffixes_and_ignore_fences(
    tmp_path: Path,
) -> None:
    markdown = tmp_path / "headings.md"
    markdown.write_text(
        "# Decision: Park the Layer (Default-Off)\n"
        "## Result\n"
        "## Result\n"
        "```md\n"
        "# Not A Heading\n"
        "```\n",
        encoding="utf-8",
    )

    assert validator.markdown_heading_slugs(markdown) == {
        "decision-park-the-layer-default-off",
        "result",
        "result-1",
    }


def test_reference_requires_exact_heading_fragment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path
    evidence = root / "docs" / "evidence.md"
    evidence.parent.mkdir()
    evidence.write_text("# Recorded Result\n", encoding="utf-8")
    monkeypatch.setattr(validator, "ROOT", root)

    assert validator.resolve_reference(
        "docs/evidence.md#recorded-result",
        source=Path("adr/ADR-999-test.md"),
    ) == []
    errors = validator.resolve_reference(
        "docs/evidence.md#missing-result",
        source=Path("adr/ADR-999-test.md"),
    )
    assert any("unresolved heading fragment" in error for error in errors)


def test_exact_key_conflict_is_rejected(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    adr_dir = root / "adr"
    docs_dir = root / "docs"
    adr_dir.mkdir()
    docs_dir.mkdir()
    (docs_dir / "evidence.md").write_text(
        "# Support\n\n# Result\n",
        encoding="utf-8",
    )
    first = adr_dir / "ADR-998-first.md"
    second = adr_dir / "ADR-999-second.md"
    write_adr(first, record(resolution_status="qualified"))
    write_adr(second, record(resolution_status="unresolved"))
    monkeypatch.setattr(validator, "ROOT", root)

    _, _, failures = validator.validate_paths([first, second])

    assert any("conflicting exact-key decisions" in error for error in failures)


def test_adr_016_proof_case_passes() -> None:
    adr = Path("adr/ADR-016-memory-layer-extension-seam.md").resolve()

    documents, records, failures = validator.validate_paths(
        sorted(Path("adr").resolve().glob("ADR-*.md"))
    )

    assert adr.exists()
    assert documents == 1
    assert records == 4
    assert failures == []

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs/projects/repository_assessment/tools/validate_probe_obligation_screen.py"
)
SPEC = importlib.util.spec_from_file_location("validate_probe_obligation_screen", SCRIPT_PATH)
assert SPEC is not None
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def test_campaign_without_freeze_manifest_fails_closed(tmp_path: Path) -> None:
    result = validator.validate_campaign(campaign_root=tmp_path, source_root=tmp_path)

    assert result["valid"] is False
    assert result["errors"] == ["missing freeze manifest"]
    assert result["recall_adjudicated"] is False


def test_gate_control_predicate_requires_real_workspace_module() -> None:
    negative = {
        "satisfied": False,
        "observed_output_present": True,
        "satisfaction_failures": ["no_workspace_module_loaded"],
    }
    positive = {
        "satisfied": True,
        "observed_output_present": True,
        "workspace_module_files": ["/workspace/pkg/src/pkg/__init__.py"],
    }

    negative_valid = (
        negative["satisfied"] is False
        and "no_workspace_module_loaded" in negative["satisfaction_failures"]
        and negative["observed_output_present"] is True
    )
    positive_valid = (
        positive["satisfied"] is True
        and positive["observed_output_present"] is True
        and any(path.startswith("/workspace/") for path in positive["workspace_module_files"])
    )

    assert negative_valid is True
    assert positive_valid is True

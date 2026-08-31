from __future__ import annotations

from agent_lib.eval.evidence_finalization import build_evidence_ledger


def _read_step(*, start: int, text: str, lines: list[int], success: bool = True) -> dict:
    return {
        "action": {
            "kind": "tool",
            "tool_call": {
                "name": "read_file",
                "arguments": {"path": "pkg/module.py", "start_line": start},
            },
        },
        "observation": {
            "text": text,
            "tool_result": {
                "success": success,
                "meta": {
                    "evidence": [{"path": "pkg/module.py", "lines": lines}],
                    "paths": ["pkg/module.py"],
                },
            },
        },
    }


def test_ledger_deduplicates_overlapping_source_lines_without_relevance_filtering() -> None:
    ledger = build_evidence_ledger(
        [
            _read_step(start=1, text="1: alpha\n2: beta", lines=[1, 2]),
            _read_step(start=2, text="2: beta\n3: gamma", lines=[2, 3]),
        ]
    )

    assert ledger.text == "### pkg/module.py\n1: alpha\n2: beta\n3: gamma"
    assert ledger.line_atoms == 3
    assert ledger.path_atoms == 0
    assert ledger.source_paths == ("pkg/module.py",)


def test_ledger_excludes_failed_results_and_retains_path_only_evidence() -> None:
    failed = _read_step(start=1, text="1: must not appear", lines=[1], success=False)
    listing = {
        "action": {
            "kind": "tool",
            "tool_call": {"name": "list_files", "arguments": {"path": "."}},
        },
        "observation": {
            "text": "pkg/other.py",
            "tool_result": {
                "success": True,
                "meta": {"paths": ["pkg/other.py"]},
            },
        },
    }

    ledger = build_evidence_ledger([failed, listing])

    assert "must not appear" not in ledger.text
    assert ledger.text == "### Observed paths\npkg/other.py"
    assert ledger.path_atoms == 1

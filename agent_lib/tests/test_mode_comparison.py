from __future__ import annotations

from pathlib import Path

from agent_lib.examples import run_integration_programming_demo, run_mode_comparison_demo


def test_integration_programming_demo_repairs_file_and_records_messages(tmp_path: Path) -> None:
    result, root = run_integration_programming_demo(root=tmp_path)

    assert (root / "main.py").read_text(encoding="utf-8").strip().endswith("return a + b")
    assert result.final_output.startswith("Accepted the patch")
    assert [message.kind for message in result.messages] == [
        "finding",
        "finding",
        "patch_proposal",
        "patch_proposal",
        "verification_result",
        "decision",
    ]
    assert result.reservations[0].status == "active"
    assert result.reservations[-1].status == "released"


def test_mode_comparison_demo_shows_same_task_in_native_and_integration_modes(
    tmp_path: Path,
) -> None:
    result = run_mode_comparison_demo(root=tmp_path, memory_backend="engram")

    native_file = result.native_root / "main.py"
    integration_file = result.integration.root / "main.py"

    assert native_file.read_text(encoding="utf-8").strip().endswith("return a + b")
    assert integration_file.read_text(encoding="utf-8").strip().endswith("return a + b")
    assert "returns a + b" in result.native_final_output
    assert result.integration.thread_id == "programming-task"
    assert len(result.integration.messages) == 6

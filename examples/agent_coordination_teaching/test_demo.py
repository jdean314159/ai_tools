from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path


def _ai_tools_imports(py_file: Path) -> list[str]:
    """
    Return every dotted import path inside `py_file` whose root package is one
    of the ai_tools packages. This is a static check — it parses the source
    without importing it, so it catches private imports even on platforms
    where the package isn't installed.
    """
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    roots = {"engram", "llm_engines", "llm_harness_core", "agent_lib", "rag_lib", "llm_inspector"}
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            head = node.module.split(".", 1)[0]
            if head in roots:
                found.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                head = alias.name.split(".", 1)[0]
                if head in roots:
                    found.append(alias.name)
    return found


def test_only_public_ai_tools_imports() -> None:
    """
    Guard: every ai_tools-package import in this example must hit the top-level
    package (i.e. resolve through that package's __all__). No reaching into
    private subpackages such as llm_engines.backends.* — that would defeat the
    point of the public-API consumer rule.
    """
    package_dir = Path(__file__).resolve().parent
    offenders: list[tuple[str, str]] = []
    for py_file in package_dir.glob("*.py"):
        for module in _ai_tools_imports(py_file):
            # Only the top-level package is the public surface.
            if "." in module:
                offenders.append((py_file.name, module))
    assert not offenders, (
        "Private ai_tools imports found in coordination example "
        f"(must use top-level package only): {offenders}"
    )


def test_mock_demo_writes_exchange_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    workspace = tmp_path / "workspace"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "examples.agent_coordination_teaching.run_demo",
            "--workers",
            "mock",
            "--run-dir",
            str(run_dir),
            "--workspace",
            str(workspace),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "exchanges.jsonl").exists()
    assert (run_dir / "trace_events.jsonl").exists()
    assert (run_dir / "messages" / "000003.md").exists()

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["workers"][0]["kind"] == "mock"

    exchanges = (run_dir / "exchanges.jsonl").read_text(encoding="utf-8")
    assert "assignment_sent" in exchanges
    assert "worker_completed" in exchanges


def test_llm_engine_dry_run_does_not_load_model(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    workspace = tmp_path / "workspace"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "examples.agent_coordination_teaching.run_demo",
            "--workers",
            "llm_engine",
            "--worker-backend",
            "llamacpp",
            "--worker-model",
            "/tmp/not-loaded-in-dry-run.gguf",
            "--worker-n-gpu-layers",
            "12",
            "--dry-run",
            "--run-dir",
            str(run_dir),
            "--workspace",
            str(workspace),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    worker = manifest["workers"][0]
    assert worker["kind"] == "llm_engine"
    assert worker["backend"] == "llamacpp"
    assert worker["model"] == "/tmp/not-loaded-in-dry-run.gguf"
    assert worker["n_gpu_layers"] == 12

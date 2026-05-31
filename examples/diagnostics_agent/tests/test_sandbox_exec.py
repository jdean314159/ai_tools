from __future__ import annotations

from pathlib import Path
from shutil import which
import subprocess

import pytest

from diagnostics_agent import ReadOnlySandbox, SandboxConfig


pytestmark = pytest.mark.skipif(which("podman") is None, reason="podman is not installed")


def test_run_reads_mounted_temp_file(tmp_path: Path) -> None:
    sample = tmp_path / "sample.log"
    sample.write_text("diagnostic sample\n", encoding="utf-8")
    tmp_path.chmod(0o755)
    sample.chmod(0o644)

    sandbox = ReadOnlySandbox(SandboxConfig(mounts=((str(tmp_path), "/logs"),)))
    result = sandbox.run(["cat", "/logs/sample.log"])

    assert result.exit_code == 0
    assert result.stdout == "diagnostic sample\n"
    assert result.timed_out is False
    assert result.inner_command == ["cat", "/logs/sample.log"]
    assert "--network" in result.argv


def test_mounted_path_is_read_only(tmp_path: Path) -> None:
    sample = tmp_path / "sample.log"
    sample.write_text("diagnostic sample\n", encoding="utf-8")
    tmp_path.chmod(0o755)
    sample.chmod(0o644)

    sandbox = ReadOnlySandbox(SandboxConfig(mounts=((str(tmp_path), "/logs"),)))
    result = sandbox.run(["sh", "-c", "echo nope >> /logs/sample.log"])

    assert result.exit_code != 0
    assert sample.read_text(encoding="utf-8") == "diagnostic sample\n"


def test_network_namespace_only_exposes_loopback() -> None:
    result = ReadOnlySandbox().run(["sh", "-c", "ls /sys/class/net | sort"])

    assert result.exit_code == 0
    assert result.stdout.split() == ["lo"]


def test_timeout_forces_teardown() -> None:
    sandbox = ReadOnlySandbox(SandboxConfig(timeout_s=2.0))
    result = sandbox.run(["sleep", "60"])
    name = _option_value(result.argv, "--name")

    ps = subprocess.run(
        ["podman", "ps", "-a", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.timed_out is True
    assert result.exit_code == 124
    assert name not in ps.stdout.splitlines()


def test_stdout_truncation_sets_flag() -> None:
    sandbox = ReadOnlySandbox(SandboxConfig(max_output_bytes=16))
    result = sandbox.run(["sh", "-c", "dd if=/dev/zero bs=1 count=128 2>/dev/null | tr '\\0' x"])

    assert result.exit_code == 0
    assert result.truncated is True
    assert result.stdout == "x" * 16


def _option_value(argv: list[str], option: str) -> str:
    index = argv.index(option)
    return argv[index + 1]

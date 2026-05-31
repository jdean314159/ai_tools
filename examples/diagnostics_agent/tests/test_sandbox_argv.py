from __future__ import annotations

import pytest

from diagnostics_agent import MountError, ReadOnlySandbox, SandboxConfig


def test_build_argv_includes_required_sandbox_flags() -> None:
    argv = ReadOnlySandbox().build_argv(["cat", "/logs/sample.log"])

    assert argv[:2] == ["podman", "run"]
    assert _option_value(argv, "--network") == "none"
    assert "--read-only" in argv
    assert _option_value(argv, "--cap-drop") == "ALL"
    assert _option_value(argv, "--security-opt") == "no-new-privileges"
    assert _option_value(argv, "--user") == "65534:65534"
    assert _option_value(argv, "--pids-limit") == "128"
    assert _option_value(argv, "--memory") == "256m"
    assert _option_value(argv, "--cpus") == "1.0"
    assert "--rm" in argv
    assert _option_value(argv, "--name").startswith("diag-sbx-")
    assert _option_value(argv, "--tmpfs") == "/tmp:rw,noexec,nosuid,nodev,size=16m"
    assert argv[-3:] == ["docker.io/library/alpine:3.20", "cat", "/logs/sample.log"]


def test_build_argv_never_emits_forbidden_flags_or_writable_mounts() -> None:
    config = SandboxConfig(mounts=(("/var/log", "/logs"),))
    argv = ReadOnlySandbox(config).build_argv(["cat", "/logs/sample.log"])

    assert "--privileged" not in argv
    assert "--cap-add" not in argv
    assert "--device" not in argv
    assert _option_value(argv, "--network") == "none"
    assert "/var/log:/logs:rw" not in argv
    assert "/var/log:/logs" not in argv
    assert _option_value(argv, "-v") == "/var/log:/logs:ro"


@pytest.mark.parametrize(
    "extra_run_args",
    [
        ("--privileged",),
        ("--cap-add", "SYS_ADMIN"),
        ("--cap-add=SYS_ADMIN",),
        ("--device", "/dev/sda"),
        ("--device=/dev/sda",),
        ("--network", "host"),
        ("--network=host",),
        ("-v", "/tmp:/host_tmp:rw"),
        ("--volume", "/tmp:/host_tmp"),
        ("--mount", "type=bind,src=/tmp,dst=/host_tmp"),
    ],
)
def test_extra_run_args_cannot_reintroduce_forbidden_runtime_flags(
    extra_run_args: tuple[str, ...],
) -> None:
    config = SandboxConfig(extra_run_args=extra_run_args)

    with pytest.raises(ValueError, match="extra_run_args cannot"):
        ReadOnlySandbox(config).build_argv(["true"])


def test_mounts_render_as_read_only_bind_mounts() -> None:
    config = SandboxConfig(
        mounts=(
            ("/var/log", "/logs"),
            ("/tmp", "/host_tmp"),
        )
    )
    argv = ReadOnlySandbox(config).build_argv(["true"])

    volume_values = [argv[index + 1] for index, item in enumerate(argv) if item == "-v"]
    assert volume_values == ["/var/log:/logs:ro", "/tmp:/host_tmp:ro"]


def test_non_default_config_propagates_to_argv() -> None:
    config = SandboxConfig(
        image="localhost/custom:latest",
        memory="64m",
        cpus="0.5",
        pids_limit=16,
        user="1000:1000",
        tmpfs_size="4m",
        runtime="docker",
        extra_run_args=("--pull", "never"),
    )

    argv = ReadOnlySandbox(config).build_argv(["id"])

    assert argv[:2] == ["docker", "run"]
    assert _option_value(argv, "--memory") == "64m"
    assert _option_value(argv, "--cpus") == "0.5"
    assert _option_value(argv, "--pids-limit") == "16"
    assert _option_value(argv, "--user") == "1000:1000"
    assert _option_value(argv, "--tmpfs") == "/tmp:rw,noexec,nosuid,nodev,size=4m"
    assert "--pull" in argv
    assert "never" in argv
    assert "localhost/custom:latest" in argv


def test_build_argv_rejects_empty_command() -> None:
    with pytest.raises(ValueError, match="command must not be empty"):
        ReadOnlySandbox().build_argv([])


def test_build_argv_rejects_relative_host_mount_path() -> None:
    config = SandboxConfig(mounts=(("relative/path", "/logs"),))

    with pytest.raises(MountError, match="host path must be absolute"):
        ReadOnlySandbox(config).build_argv(["true"])


def test_build_argv_rejects_relative_container_mount_path() -> None:
    config = SandboxConfig(mounts=(("/var/log", "logs"),))

    with pytest.raises(MountError, match="container path must be absolute"):
        ReadOnlySandbox(config).build_argv(["true"])


def _option_value(argv: list[str], option: str) -> str:
    index = argv.index(option)
    return argv[index + 1]

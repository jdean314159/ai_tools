from __future__ import annotations

import json
import os
import urllib.error
from unittest.mock import patch

import pytest

from diagnostics_agent.collect import JOURNAL_OUTPUT_FIELDS, journalctl_collector
from diagnostics_agent.models import ModelDiscoveryError, estimate_fit, list_local_models
from diagnostics_agent.sandbox import make_staging_sandbox


@pytest.mark.parametrize(
    ("size", "vram", "expected"),
    [
        (10, None, "unknown"),
        (100, 120, "fits"),
        (100, 110, "tight"),
        (100, 80, "unlikely"),
    ],
)
def test_estimate_fit(size: int, vram: int | None, expected: str) -> None:
    assert estimate_fit(size, vram) == expected


def test_list_local_models_parses_ollama_tags_and_fit() -> None:
    payload = {
        "models": [
            {"name": "qwen3:8b", "size": 5_000},
            {"name": "qwen3:27b", "size": 17_000},
        ]
    }

    with patch("urllib.request.urlopen", return_value=_FakeResponse(payload)):
        models = list_local_models(available_vram_bytes=20_400)

    assert [model.name for model in models] == ["qwen3:27b", "qwen3:8b"]
    assert [model.fit for model in models] == ["fits", "fits"]
    assert models[0].size_bytes == 17_000


def test_list_local_models_raises_typed_error_on_connection_failure() -> None:
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
        with pytest.raises(ModelDiscoveryError):
            list_local_models(available_vram_bytes=1)


def test_journalctl_collector_builds_json_argv() -> None:
    collector = journalctl_collector(priority="error", since="-6h")

    assert collector.command == [
        "journalctl",
        "-o",
        "json",
        "-p",
        "error",
        "--since",
        "-6h",
        "--no-pager",
        "--output-fields="
        "MESSAGE,PRIORITY,__REALTIME_TIMESTAMP,__TIMESTAMP,_SOURCE_REALTIME_TIMESTAMP,"
        "_HOSTNAME,HOSTNAME,SYSLOG_IDENTIFIER,_COMM,_EXE,_PID,SYSLOG_PID,"
        "CONTAINER_NAME,container_name,_CONTAINER_NAME",
    ]
    assert isinstance(collector.command, list)


def test_journalctl_projection_covers_triage_journal_fields() -> None:
    required_fields = {
        "MESSAGE",
        "PRIORITY",
        "__REALTIME_TIMESTAMP",
        "__TIMESTAMP",
        "_SOURCE_REALTIME_TIMESTAMP",
        "_HOSTNAME",
        "HOSTNAME",
        "SYSLOG_IDENTIFIER",
        "_COMM",
        "_EXE",
        "_PID",
        "SYSLOG_PID",
        "CONTAINER_NAME",
        "container_name",
        "_CONTAINER_NAME",
    }

    collector = journalctl_collector(priority="warning", since="-24h")
    projection_args = [arg for arg in collector.command if arg.startswith("--output-fields=")]

    assert set(JOURNAL_OUTPUT_FIELDS) >= required_fields
    assert len(projection_args) == 1
    assert set(projection_args[0].removeprefix("--output-fields=").split(",")) >= required_fields


def test_journalctl_collector_rejects_invalid_priority() -> None:
    with pytest.raises(ValueError, match="priority"):
        journalctl_collector(priority="info", since="-24h")


@pytest.mark.parametrize("since", ["yesterday; rm -rf /", "-24m", "last week"])
def test_journalctl_collector_rejects_malformed_since(since: str) -> None:
    with pytest.raises(ValueError, match="since"):
        journalctl_collector(priority="warning", since=since)


def test_make_staging_sandbox_uses_keep_id_and_current_user() -> None:
    sandbox = make_staging_sandbox()

    assert sandbox.config.user == f"{os.getuid()}:{os.getgid()}"
    assert sandbox.config.extra_run_args == ("--userns=keep-id",)


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

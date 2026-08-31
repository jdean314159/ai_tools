from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import re
import subprocess

_ALLOWED_PRIORITIES = ("emergency", "alert", "critical", "error", "warning")
_SINCE_RE = re.compile(
    r"^(?:-\d+[hd]|[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[ T][0-9]{2}:[0-9]{2}(?::[0-9]{2})?)?)$"
)
JOURNAL_OUTPUT_FIELDS = (
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
)


@dataclass(frozen=True)
class CollectedLogs:
    staging_path: Path
    command: list[str]
    source_description: str
    byte_count: int

    def to_dict(self) -> dict:
        return {
            "staging_path": str(self.staging_path),
            "command": list(self.command),
            "source_description": self.source_description,
            "byte_count": self.byte_count,
        }


class Collector(Protocol):
    def collect(self, staging_dir: Path) -> CollectedLogs: ...


class CommandCollector:
    """Run a fixed host-side read-only command and stage stdout for sandbox reading."""

    def __init__(
        self,
        command: list[str],
        *,
        source_description: str,
        timeout_s: float = 30.0,
    ) -> None:
        if not command:
            raise ValueError("command must not be empty")
        self.command = list(command)
        self.source_description = source_description
        self.timeout_s = timeout_s

    def collect(self, staging_dir: Path) -> CollectedLogs:
        staging_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        completed = subprocess.run(
            self.command,
            capture_output=True,
            text=True,
            timeout=self.timeout_s,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"collection command failed with exit code {completed.returncode}: {completed.stderr}"
            )

        staging_path = staging_dir / "collected.log"
        staging_path.write_text(completed.stdout, encoding="utf-8")
        staging_path.chmod(0o600)
        return CollectedLogs(
            staging_path=staging_path,
            command=list(self.command),
            source_description=self.source_description,
            byte_count=len(completed.stdout.encode("utf-8")),
        )


def journalctl_collector(*, priority: str = "warning", since: str = "-24h") -> CommandCollector:
    normalized_priority = priority.strip().lower()
    if normalized_priority not in _ALLOWED_PRIORITIES:
        raise ValueError(f"priority must be one of: {', '.join(_ALLOWED_PRIORITIES)}")
    if not _SINCE_RE.fullmatch(since.strip()):
        raise ValueError("since must be a relative window like -24h/-3d or an ISO date/time")
    command = [
        "journalctl",
        "-o",
        "json",
        "-p",
        normalized_priority,
        "--since",
        since.strip(),
        "--no-pager",
        f"--output-fields={','.join(JOURNAL_OUTPUT_FIELDS)}",
    ]
    return CommandCollector(
        command,
        source_description=f"journalctl json priority <= {normalized_priority} since {since.strip()}",
    )

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import platform
import socket


@dataclass(frozen=True)
class SystemFacts:
    hostname: str | None
    kernel_release: str | None
    kernel_version: str | None
    os_name: str | None
    os_version: str | None
    arch: str | None

    def to_dict(self) -> dict:
        return {
            "hostname": self.hostname,
            "kernel_release": self.kernel_release,
            "kernel_version": self.kernel_version,
            "os_name": self.os_name,
            "os_version": self.os_version,
            "arch": self.arch,
        }

    def as_prompt_block(self) -> str:
        lines = ["Verified host facts (authoritative -- do not contradict or invent beyond these):"]
        if self.hostname:
            lines.append(f"- hostname: {self.hostname}")
        if self.os_name:
            lines.append(f"- os: {self.os_name}")
        if self.os_version:
            lines.append(f"- os version: {self.os_version}")
        if self.kernel_release:
            lines.append(f"- kernel: {self.kernel_release}")
        if self.kernel_version:
            lines.append(f"- kernel version: {self.kernel_version}")
        if self.arch:
            lines.append(f"- arch: {self.arch}")
        if len(lines) == 1:
            return "No verified host facts are available; do not state OS, kernel, or hostname."
        lines.append("Any fact not listed above is unknown; do not state it.")
        return "\n".join(lines)


def collect_system_facts() -> SystemFacts:
    os_release = _parse_os_release(Path("/etc/os-release"))
    return SystemFacts(
        hostname=_nonempty(platform.node()) or _nonempty(socket.gethostname()),
        kernel_release=_nonempty(platform.release()),
        kernel_version=_nonempty(platform.version()),
        os_name=os_release.get("PRETTY_NAME") or os_release.get("NAME"),
        os_version=os_release.get("VERSION_ID"),
        arch=_nonempty(platform.machine()),
    )


def _parse_os_release(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}

    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_os_release_quotes(value.strip())
        if key:
            values[key] = value
    return values


def _strip_os_release_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _nonempty(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned or None

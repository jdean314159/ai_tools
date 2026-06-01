from __future__ import annotations

from diagnostics_agent.system_facts import SystemFacts, _parse_os_release


def test_os_release_parse_prefers_pretty_name_and_version_id(tmp_path) -> None:
    os_release = tmp_path / "os-release"
    os_release.write_text(
        'NAME="Ubuntu"\nPRETTY_NAME="Ubuntu 25.10"\nVERSION_ID="25.10"\n',
        encoding="utf-8",
    )

    parsed = _parse_os_release(os_release)
    facts = SystemFacts(
        hostname=None,
        kernel_release=None,
        kernel_version=None,
        os_name=parsed.get("PRETTY_NAME") or parsed.get("NAME"),
        os_version=parsed.get("VERSION_ID"),
        arch=None,
    )

    assert facts.os_name == "Ubuntu 25.10"
    assert facts.os_version == "25.10"


def test_os_release_parse_strips_quotes_and_allows_missing_version(tmp_path) -> None:
    os_release = tmp_path / "os-release"
    os_release.write_text("NAME=Fedora Linux\nPRETTY_NAME='Fedora Linux 42'\n", encoding="utf-8")

    parsed = _parse_os_release(os_release)

    assert parsed["NAME"] == "Fedora Linux"
    assert parsed["PRETTY_NAME"] == "Fedora Linux 42"
    assert parsed.get("VERSION_ID") is None


def test_os_release_absent_returns_empty_mapping(tmp_path) -> None:
    parsed = _parse_os_release(tmp_path / "missing-os-release")

    assert parsed == {}


def test_prompt_block_omits_unknown_lines() -> None:
    facts = SystemFacts(
        hostname=None,
        kernel_release="6.17.0-23-generic",
        kernel_version=None,
        os_name="Ubuntu 25.10",
        os_version="25.10",
        arch="x86_64",
    )

    block = facts.as_prompt_block()

    assert "Verified host facts" in block
    assert "- os: Ubuntu 25.10" in block
    assert "- os version: 25.10" in block
    assert "- kernel: 6.17.0-23-generic" in block
    assert "- arch: x86_64" in block
    assert "hostname:" not in block
    assert "Any fact not listed above is unknown" in block


def test_all_none_prompt_block_uses_unknown_sentinel() -> None:
    facts = SystemFacts(
        hostname=None,
        kernel_release=None,
        kernel_version=None,
        os_name=None,
        os_version=None,
        arch=None,
    )

    assert (
        facts.as_prompt_block()
        == "No verified host facts are available; do not state OS, kernel, or hostname."
    )

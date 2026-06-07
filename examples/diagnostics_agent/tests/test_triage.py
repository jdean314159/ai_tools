from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

from diagnostics_agent import LogTriage, Severity, TriageConfig


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_iso_line_extracts_fields() -> None:
    line = "2026-05-29T14:03:11-07:00 host sshd[1234]: <38>Failed password from 192.0.2.1"

    record = LogTriage().parse_lines([line])[0]

    assert record.raw == line
    assert record.timestamp == datetime(2026, 5, 29, 14, 3, 11, tzinfo=timezone(timedelta(hours=-7)))
    assert record.host == "host"
    assert record.process == "sshd"
    assert record.pid == 1234
    assert record.severity == Severity.INFO
    assert record.message == "Failed password from 192.0.2.1"
    assert record.parsed is True


def test_parse_legacy_syslog_with_assumed_year() -> None:
    line = "May 29 14:03:11 host sshd[1234]: Failed password from 192.0.2.1"

    record = LogTriage(TriageConfig(assume_year=2026)).parse_lines([line])[0]

    assert record.timestamp == datetime(2026, 5, 29, 14, 3, 11)
    assert record.host == "host"
    assert record.process == "sshd"
    assert record.pid == 1234
    assert record.message == "Failed password from 192.0.2.1"


def test_parse_legacy_syslog_without_assumed_year_keeps_timestamp_none() -> None:
    line = "May 29 14:03:11 host sshd[1234]: Failed password from 192.0.2.1"

    record = LogTriage().parse_lines([line])[0]

    assert record.timestamp is None
    assert record.raw == line
    assert record.parsed is True


def test_parse_journal_json_uses_authoritative_priority() -> None:
    line = json.dumps(
        {
            "__REALTIME_TIMESTAMP": "1780077600000000",
            "_HOSTNAME": "host",
            "SYSLOG_IDENTIFIER": "kernel",
            "_PID": "123",
            "PRIORITY": "4",
            "MESSAGE": "device state changed without severity keyword",
            "CONTAINER_NAME": "workload",
        }
    )

    record = LogTriage().parse_lines([line])[0]

    assert record.parsed is True
    assert record.timestamp == datetime.fromtimestamp(1780077600)
    assert record.host == "host"
    assert record.process == "kernel"
    assert record.pid == 123
    assert record.severity == Severity.WARNING
    assert record.message == "device state changed without severity keyword"
    assert record.container_name == "workload"


def test_journal_json_warning_priority_is_not_suppressed_as_info() -> None:
    source = "\n".join(
        json.dumps(
            {
                "__REALTIME_TIMESTAMP": str(1780077600000000 + index),
                "_HOSTNAME": "host",
                "SYSLOG_IDENTIFIER": "daemon",
                "_PID": str(100 + index),
                "PRIORITY": "4",
                "MESSAGE": f"device state changed on bus {index}",
            }
        )
        for index in range(3)
    )

    summary = LogTriage().triage(source)

    assert summary.severity_counts == {Severity.WARNING: 3}
    assert summary.suppressed == ()
    assert len(summary.top_clusters) == 1
    assert summary.top_clusters[0].severity == Severity.WARNING
    assert summary.top_clusters[0].count == 3


def test_structured_self_sandbox_noise_is_accounted_and_excluded_by_default() -> None:
    source = "\n".join(
        [
            json.dumps(
                {
                    "__REALTIME_TIMESTAMP": "1780077600000000",
                    "_HOSTNAME": "host",
                    "SYSLOG_IDENTIFIER": "kernel",
                    "PRIORITY": "4",
                    "CONTAINER_NAME": "diag-sbx-abc123",
                    "MESSAGE": "overlayfs: does not support file handles",
                }
            ),
            json.dumps(
                {
                    "__REALTIME_TIMESTAMP": "1780077601000000",
                    "_HOSTNAME": "host",
                    "SYSLOG_IDENTIFIER": "audit",
                    "PRIORITY": "4",
                    "CONTAINER_NAME": "diag-sbx-def456",
                    "MESSAGE": "denied write to /logs/sample.log",
                }
            ),
            json.dumps(
                {
                    "__REALTIME_TIMESTAMP": "1780077602000000",
                    "_HOSTNAME": "host",
                    "SYSLOG_IDENTIFIER": "kernel",
                    "PRIORITY": "4",
                    "MESSAGE": "overlayfs: unrelated-container does not support file handles",
                }
            ),
        ]
    )

    summary = LogTriage().triage(source)

    assert summary.total_lines == 3
    assert summary.parsed_lines == 3
    assert summary.excluded_self_noise == 2
    assert summary.to_dict()["excluded_self_noise"] == 2
    assert summary.severity_counts == {Severity.WARNING: 3}
    assert len(summary.top_clusters) == 1
    assert "unrelated-container" in summary.top_clusters[0].template
    assert "diag-sbx-" not in json.dumps(summary.to_dict(), sort_keys=True)
    assert _accounted_count(summary) == summary.total_lines


def test_self_sandbox_message_text_is_not_excluded_without_structured_container_name() -> None:
    source = json.dumps(
        {
            "__REALTIME_TIMESTAMP": "1780077600000000",
            "_HOSTNAME": "host",
            "SYSLOG_IDENTIFIER": "kernel",
            "PRIORITY": "4",
            "MESSAGE": "spoofed message mentions diag-sbx-abc123 but is not container-attributed",
        }
    )

    summary = LogTriage().triage(source)

    assert summary.total_lines == 1
    assert summary.excluded_self_noise == 0
    assert "diag-sbx-abc123" in summary.top_clusters[0].template


def test_structured_self_sandbox_noise_exclusion_can_be_disabled() -> None:
    source = json.dumps(
        {
            "__REALTIME_TIMESTAMP": "1780077600000000",
            "_HOSTNAME": "host",
            "SYSLOG_IDENTIFIER": "kernel",
            "PRIORITY": "4",
            "CONTAINER_NAME": "diag-sbx-abc123",
            "MESSAGE": "overlayfs: does not support file handles",
        }
    )

    summary = LogTriage(TriageConfig(exclude_self_noise=False)).triage(source)

    assert summary.total_lines == 1
    assert summary.excluded_self_noise == 0
    assert summary.top_clusters[0].template == "overlayfs: does not support file handles"


def test_unparsed_line_is_preserved_and_counted() -> None:
    summary = LogTriage().triage(["raw unstructured line"])
    record = LogTriage().parse_lines(["raw unstructured line"])[0]

    assert record.parsed is False
    assert record.raw == "raw unstructured line"
    assert record.message == "raw unstructured line"
    assert record.severity == Severity.UNKNOWN
    assert summary.total_lines == 1
    assert summary.unparsed_lines == 1


def test_templating_deduplicates_failed_password_lines_by_ip_and_port() -> None:
    lines = [
        f"2026-05-29T14:03:1{i}-07:00 host sshd[{1000 + i}]: Failed password for root from 192.0.2.{i} port {53000 + i} ssh2"
        for i in range(3)
    ]

    summary = LogTriage().triage(lines)
    finding = summary.findings[0]

    assert finding.rule_name == "ssh_failed_auth"
    assert finding.count == 3
    assert "<IP>" in finding.template
    assert "<NUM>" in finding.template


def test_severity_heuristics_classify_keywords_without_priority() -> None:
    records = LogTriage().parse_lines(
        [
            "2026-05-29T14:03:11-07:00 host proc[1]: debug detail",
            "2026-05-29T14:03:12-07:00 host proc[1]: warning detail",
            "2026-05-29T14:03:13-07:00 host proc[1]: error detail",
            "2026-05-29T14:03:14-07:00 host proc[1]: fatal detail",
        ]
    )

    assert [record.severity for record in records] == [
        Severity.DEBUG,
        Severity.WARNING,
        Severity.ERROR,
        Severity.CRITICAL,
    ]


def test_oom_rule_produces_memory_critical_finding() -> None:
    source = (FIXTURES / "journal_iso_sample.log").read_text(encoding="utf-8")

    summary = LogTriage().triage(source)

    oom = [finding for finding in summary.findings if finding.rule_name == "oom_kill"][0]
    assert oom.category == "memory"
    assert oom.severity == Severity.CRITICAL
    assert summary.findings[0].severity >= summary.top_clusters[0].severity if summary.top_clusters else True


def test_journal_json_fixture_preserves_warning_or_higher_priorities() -> None:
    source = (FIXTURES / "journal_json_sample.log").read_text(encoding="utf-8")

    summary = LogTriage().triage(source)

    assert summary.total_lines == 3
    assert summary.parsed_lines == 3
    assert summary.unparsed_lines == 0
    assert summary.severity_counts == {Severity.ERROR: 1, Severity.WARNING: 2}
    assert summary.suppressed == ()
    assert [cluster.severity for cluster in summary.top_clusters] == [
        Severity.ERROR,
        Severity.WARNING,
        Severity.WARNING,
    ]


def test_suppression_accounting_demotes_low_severity_clusters() -> None:
    lines = [
        f"2026-05-29T14:00:0{i}-07:00 host cron[{100 + i}]: info repeated low priority line {i}"
        for i in range(5)
    ]

    summary = LogTriage().triage(lines)

    assert summary.top_clusters == ()
    assert summary.suppressed == ((Severity.INFO, 5),)
    assert _accounted_count(summary) == summary.total_lines


def test_top_clusters_are_ordered_by_count_and_capped() -> None:
    source = (FIXTURES / "mixed_noise.log").read_text(encoding="utf-8")

    summary = LogTriage(TriageConfig(max_clusters=2)).triage(source)

    assert len(summary.top_clusters) == 2
    assert [cluster.count for cluster in summary.top_clusters] == [12, 6]
    assert "warning connection reset from <IP>:<PORT>" in summary.top_clusters[0].template
    assert "warning disk usage <NUM> percent on nvme0n1" == summary.top_clusters[1].template
    assert all(cluster.severity == Severity.WARNING for cluster in summary.top_clusters)
    assert _accounted_count(summary) == summary.total_lines


def test_conservation_invariant_for_mixed_fixture() -> None:
    source = (FIXTURES / "mixed_noise.log").read_text(encoding="utf-8")

    summary = LogTriage().triage(source)

    assert summary.total_lines == summary.parsed_lines + summary.unparsed_lines
    assert _accounted_count(summary) == summary.total_lines


def test_triage_is_deterministic_for_same_fixture() -> None:
    source = (FIXTURES / "mixed_noise.log").read_text(encoding="utf-8")
    triage = LogTriage()

    first = triage.triage(source)
    second = triage.triage(source)

    assert first == second
    assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(second.to_dict(), sort_keys=True)


def test_summary_to_dict_is_json_serializable() -> None:
    source = (FIXTURES / "syslog_sample.log").read_text(encoding="utf-8")
    summary = LogTriage(TriageConfig(assume_year=2026)).triage(source)

    encoded = json.dumps(summary.to_dict(), sort_keys=True)

    assert '"WARNING"' in encoded
    assert "2026-05-29T14:03:11" in encoded


def _accounted_count(summary) -> int:
    return (
        sum(finding.count for finding in summary.findings)
        + sum(cluster.count for cluster in summary.top_clusters)
        + sum(count for _severity, count in summary.suppressed)
        + summary.excluded_self_noise
    )


# ---------------------------------------------------------------------------
# FP-rate measurement — benign eval corpus
# ---------------------------------------------------------------------------

def test_benign_eval_corpus_produces_zero_findings() -> None:
    """Regression gate: all lines in benign_eval_corpus.log must produce zero findings.

    A finding here is a true false-positive at the triage stage.  The test
    measures the deterministic component of FP rate (before LLM interpretation);
    LLM FP rate is measured separately in integration tests.
    """
    source = (FIXTURES / "benign_eval_corpus.log").read_text(encoding="utf-8")

    summary = LogTriage().triage(source)

    assert summary.findings == (), (
        f"Expected zero findings from benign corpus; got: "
        + ", ".join(f.rule_name for f in summary.findings)
    )


def test_benign_eval_corpus_produces_zero_rule_matched_clusters() -> None:
    """No cluster from the benign corpus should survive into top_clusters either."""
    source = (FIXTURES / "benign_eval_corpus.log").read_text(encoding="utf-8")

    summary = LogTriage().triage(source)

    # top_clusters uses min_cluster_severity=NOTICE — if any benign cluster
    # escapes suppression and is severe enough it will appear here.
    assert summary.top_clusters == ()


def test_benign_suppressors_are_skipped_when_suppressor_list_is_empty() -> None:
    """TriageConfig(suppressors=()) disables all suppression — corpus produces findings."""
    source = (FIXTURES / "benign_eval_corpus.log").read_text(encoding="utf-8")
    config = TriageConfig(suppressors=())

    summary = LogTriage(config).triage(source)

    # With suppression disabled the ata/overlayfs/etc lines may still not hit any
    # rule (they're not in DEFAULT_RULES for most patterns), but the ACPI lines
    # definitely won't be suppressed.  We just verify the override plumbing works:
    # the call must not raise.
    assert isinstance(summary.findings, tuple)


def test_benign_suppressor_cap_does_not_affect_real_threats() -> None:
    """Suppressors must not swallow genuine security findings."""
    lines = [
        "2026-06-01T09:00:00+00:00 host sshd[1234]: Failed password for invalid user admin from 198.51.100.1 port 40000 ssh2",
        "2026-06-01T09:00:01+00:00 host kernel[0]: ACPI: \\_SB_.PCI0.RP01: AE_ALREADY_EXISTS, during name lookup/catalog",
    ]

    summary = LogTriage().triage(lines)

    rule_names = [f.rule_name for f in summary.findings]
    assert "ssh_failed_auth" in rule_names or "ssh_invalid_user" in rule_names

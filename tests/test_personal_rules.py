from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from mail_lib.indexer import MailIndex
from mail_lib.personal_rules import (
    RuleAction,
    PersonalRule,
    apply_to_message,
    classify_message,
    format_validation_report,
    load_personal_rules,
    match_rule,
    select_personal_rule,
)
from mail_lib.thunderbird import MailMessage, _html_to_text, iter_messages
from mail_lib.triage import (
    Priority,
    SELFMAIL_LINK_MAX_PROSE_CHARS,
    TriageResult,
    _is_bare_link,
    triage_message,
)
from scripts import mail_triage


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "mail_lib"
RULE_FIXTURE = FIXTURE_ROOT / "personal_rules.toml"


def _message(
    *,
    header_message_id: str = "personal-rule-message@example.test",
    sender: str = "sender@example.test",
    subject: str = "Fixture project update",
    body: str = "Synthetic fixture body.",
    recipients: tuple[str, ...] = ("user@example.test",),
) -> MailMessage:
    return MailMessage(
        header_message_id=header_message_id,
        subject=subject,
        body=body,
        sender=sender,
        recipients=recipients,
        date=None,
        source_folder="INBOX",
    )


def _result(message: MailMessage, priority: Priority = Priority.LOW) -> TriageResult:
    return TriageResult(
        header_message_id=message.header_message_id,
        priority=priority,
        reason="Built-in fixture reason.",
        matched_rules=("fixture:built-in",),
    )


def _write_rules(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_rule_fixture_loads_and_uses_one_based_indices() -> None:
    loaded = load_personal_rules(RULE_FIXTURE)

    assert loaded.ok
    assert [rule.index for rule in loaded.rules] == [1, 2, 3]
    assert loaded.rules[0].specificity == (1, 3)
    assert loaded.rules[1].specificity == (2, 3)
    assert not loaded.errors
    assert all(rule.action == RuleAction.NONE for rule in loaded.rules)


def test_action_is_validated_and_propagated_without_a_second_matcher(tmp_path: Path) -> None:
    loaded = load_personal_rules(
        _write_rules(
            tmp_path / "actions.toml",
            "[[rule]]\nsender = 'sender@example.test'\npriority = 'low'\naction = 'summarize'\n",
        )
    )
    message = _message()

    assert loaded.ok
    assert select_personal_rule(message, loaded.rules) is loaded.rules[0]
    classified = classify_message(message, loaded.rules)
    assert classified.action == RuleAction.SUMMARIZE
    assert classified.triage.priority == Priority.LOW
    assert classified.matched_personal_rule_index == 1


@pytest.mark.parametrize("value", ["hide", 7])
def test_invalid_action_rejects_entire_file(tmp_path: Path, value: object) -> None:
    rendered = repr(value).lower() if isinstance(value, str) else str(value)
    loaded = load_personal_rules(
        _write_rules(
            tmp_path / "bad-action.toml",
            f"[[rule]]\nsender = 'sender@example.test'\npriority = 'low'\naction = {rendered}\n",
        )
    )

    assert not loaded.ok
    assert "action must" in " ".join(loaded.errors)


def test_sender_domain_subject_matching_and_specificity() -> None:
    loaded = load_personal_rules(RULE_FIXTURE)
    message = _message(sender=" CEO@EXAMPLE.TEST ", subject="Weekly Newsletter: fixture")

    assert match_rule(loaded.rules[0], message)
    assert match_rule(loaded.rules[1], message)
    applied = apply_to_message(_result(message), message, loaded.rules)

    assert applied.priority == Priority.NORMAL
    assert applied.reason == "Fixture newsletter rescue."
    assert applied.matched_rules[-1] == "personal:2"


def test_domain_rule_requires_an_address_domain() -> None:
    rule = PersonalRule(
        index=1,
        sender=None,
        domain="example.test",
        subject=None,
        priority=Priority.URGENT,
        note=None,
        specificity=(1, 2),
    )
    assert not match_rule(rule, _message(sender="example.test"))


def test_subject_match_is_case_insensitive_and_default_note_is_generated() -> None:
    loaded = load_personal_rules(RULE_FIXTURE)
    message = _message(subject="UNINDEXED LOCAL NOTE")

    applied = apply_to_message(_result(message), message, loaded.rules)

    assert applied.priority == Priority.URGENT
    assert applied.reason == "Matched personal rule #3."
    assert applied.matched_rules[-1] == "personal:3"


def test_no_matching_rule_returns_built_in_result_unchanged() -> None:
    loaded = load_personal_rules(RULE_FIXTURE)
    message = _message(sender="nobody@unmatched.test", subject="Unmatched subject")
    built_in = _result(message)

    assert apply_to_message(built_in, message, loaded.rules) is built_in


def test_apply_to_message_rejects_mismatched_ids() -> None:
    message = _message(header_message_id="message@example.test")
    wrong_result = TriageResult(
        header_message_id="other@example.test",
        priority=Priority.NORMAL,
        reason="Wrong message.",
        matched_rules=("default:normal",),
    )

    with pytest.raises(ValueError, match="do not match"):
        apply_to_message(wrong_result, message, ())


def test_later_file_entry_breaks_equal_specificity_ties(tmp_path: Path) -> None:
    rules_path = _write_rules(
        tmp_path / "ties.toml",
        """
[[rule]]
subject = "project"
priority = "low"

[[rule]]
subject = "project update"
priority = "urgent"
""",
    )
    loaded = load_personal_rules(rules_path)
    message = _message(subject="Fixture project update")

    applied = apply_to_message(_result(message), message, loaded.rules)

    assert applied.priority == Priority.URGENT
    assert applied.matched_rules[-1] == "personal:2"
    assert any("nested subject" in warning for warning in loaded.warnings)


@pytest.mark.parametrize(
    "content, expected",
    [
        ("[[rule]]\npriority = 'urgent'\n", "at least one"),
        ("[[rule]]\nsender = 7\npriority = 'urgent'\n", "sender must be a string"),
        ("[[rule]]\nsubject = '   '\npriority = 'urgent'\n", "subject must not be empty"),
        ("[[rule]]\ndomain = 'user@example.test'\npriority = 'urgent'\n", "must not contain"),
        (
            "[[rule]]\nsender = 'user@example.test'\ndomain = 'example.test'\npriority = 'urgent'\n",
            "must not appear",
        ),
        ("[[rule]]\nsender = 'user@example.test'\n", "priority is required"),
        ("[[rule]]\nsender = 'user@example.test'\npriority = 1\n", "priority is required"),
        (
            "[[rule]]\nsender = 'user@example.test'\npriority = 'critical'\n",
            "priority must be one of",
        ),
        (
            "[[rule]]\nsender = 'user@example.test'\npriority = 'urgent'\nunknown = true\n",
            "unknown key",
        ),
        ("unknown = true\n", "Unknown top-level"),
        (
            "[rule]\nsender = 'user@example.test'\npriority = 'urgent'\n",
            "array of tables",
        ),
        (
            "[[rule]]\nsender = 'user@example.test'\npriority = 'urgent'\nnote = 3\n",
            "note must be a string",
        ),
    ],
)
def test_invalid_rule_shapes_reject_the_entire_file(
    tmp_path: Path,
    content: str,
    expected: str,
) -> None:
    loaded = load_personal_rules(_write_rules(tmp_path / "invalid.toml", content))

    assert not loaded.ok
    assert loaded.rules == ()
    assert expected in " ".join(loaded.errors)


@pytest.mark.parametrize("content", ["", "rule = []\n"])
def test_empty_ruleset_is_valid(tmp_path: Path, content: str) -> None:
    loaded = load_personal_rules(_write_rules(tmp_path / "empty.toml", content))

    assert loaded.ok
    assert loaded.rules == ()


def test_blank_note_is_treated_as_omitted(tmp_path: Path) -> None:
    loaded = load_personal_rules(
        _write_rules(
            tmp_path / "blank-note.toml",
            "[[rule]]\nsubject = 'fixture'\npriority = 'urgent'\nnote = '   '\n",
        )
    )
    message = _message(subject="Fixture subject")

    assert loaded.ok
    assert loaded.rules[0].note is None
    assert apply_to_message(_result(message), message, loaded.rules).reason == (
        "Matched personal rule #1."
    )


def test_collision_warnings_are_narrow(tmp_path: Path) -> None:
    distinct = load_personal_rules(
        _write_rules(
            tmp_path / "distinct.toml",
            """
[[rule]]
sender = "one@example.test"
priority = "urgent"
[[rule]]
sender = "two@example.test"
priority = "low"
""",
        )
    )
    duplicates = load_personal_rules(
        _write_rules(
            tmp_path / "duplicates.toml",
            """
[[rule]]
sender = "same@example.test"
priority = "urgent"
[[rule]]
sender = "SAME@example.test"
priority = "low"
""",
        )
    )

    assert distinct.warnings == ()
    assert any("identical predicates" in warning for warning in duplicates.warnings)


def test_validation_report_contains_rules_specificity_warnings_and_errors(tmp_path: Path) -> None:
    valid = load_personal_rules(RULE_FIXTURE)
    invalid = load_personal_rules(
        _write_rules(tmp_path / "invalid.toml", "[[rule]]\npriority = 'urgent'\n")
    )

    valid_report = format_validation_report(valid)
    invalid_report = format_validation_report(invalid)

    assert "Status: valid (3 rule(s))" in valid_report
    assert "Rule #1" in valid_report
    assert "specificity=(1, 3)" in valid_report
    assert "Status: invalid" in invalid_report
    assert "Error:" in invalid_report


@pytest.mark.parametrize("content", ["[[rule]\n", "rule = { broken = "])
def test_malformed_toml_is_reported_without_raising(tmp_path: Path, content: str) -> None:
    loaded = load_personal_rules(_write_rules(tmp_path / "malformed.toml", content))

    assert not loaded.ok
    assert loaded.rules == ()
    assert "Could not load rules file" in loaded.errors[0]


def test_bare_link_detector_boundaries_and_multiple_urls() -> None:
    url = "https://fixture.example.test/article"

    assert not _is_bare_link("")
    assert _is_bare_link(f"{'x' * SELFMAIL_LINK_MAX_PROSE_CHARS} {url}")
    assert not _is_bare_link(f"{'x' * (SELFMAIL_LINK_MAX_PROSE_CHARS + 1)} {url}")
    assert _is_bare_link(f"{url} https://fixture.example.test/second")


def test_self_mail_uses_graduated_link_floor() -> None:
    bare_link = _message(
        sender="user@example.test",
        recipients=("user@example.test",),
        body="Read this https://fixture.example.test/article",
    )
    linkless = _message(
        sender="user@example.test",
        recipients=("user@example.test",),
        body="Synthetic platform transfer without a URL.",
    )

    link_result = triage_message(bare_link)
    linkless_result = triage_message(linkless)

    assert link_result.priority == Priority.NORMAL
    assert link_result.matched_rules[-1] == "self-mail:link"
    assert linkless_result.priority == Priority.LOW
    assert linkless_result.matched_rules[-1] == "self-mail"


def test_html_href_survives_with_entities_decoded_and_non_http_excluded() -> None:
    html_body = '<p>Read <a href="https://fixture.example.test/article?a=1&amp;b=2">this</a></p>'
    non_http = '<a href="&#109;ailto:user@example.test">mail</a>'

    converted = _html_to_text(html_body)

    assert "https://fixture.example.test/article?a=1&b=2" in converted
    assert "&amp;" not in converted
    assert "mailto:" not in _html_to_text(non_http)
    assert _is_bare_link(converted)


def test_personal_rule_can_override_either_self_mail_floor(tmp_path: Path) -> None:
    loaded = load_personal_rules(
        _write_rules(
            tmp_path / "self.toml",
            "[[rule]]\nsubject = 'fixture project'\npriority = 'urgent'\n",
        )
    )
    for body in ("No link.", "https://fixture.example.test/article"):
        message = _message(
            sender="user@example.test",
            recipients=("user@example.test",),
            body=body,
        )
        applied = apply_to_message(triage_message(message), message, loaded.rules)
        assert applied.priority == Priority.URGENT


def test_cli_absent_default_rules_is_a_successful_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-config"))

    exit_code = mail_triage.main(["--profile", str(FIXTURE_ROOT), "--no-index"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "MAIL-00 Digest" in captured.out
    assert captured.err == ""


def test_cli_explicit_missing_rules_exits_before_mail_or_index_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        mail_triage,
        "iter_messages",
        lambda _profile: pytest.fail("mail must not be read"),
    )
    monkeypatch.setattr(
        mail_triage,
        "MailIndex",
        lambda _path: pytest.fail("index must not be opened"),
    )

    exit_code = mail_triage.main(["--rules", str(tmp_path / "missing.toml")])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "does not exist" in captured.err


def test_cli_validate_rules_never_reads_mail_or_index(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        mail_triage,
        "iter_messages",
        lambda _profile: pytest.fail("mail must not be read"),
    )
    monkeypatch.setattr(
        mail_triage,
        "MailIndex",
        lambda _path: pytest.fail("index must not be opened"),
    )

    exit_code = mail_triage.main(["--validate-rules", "--rules", str(RULE_FIXTURE)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Status: valid" in captured.out
    assert captured.err == ""


def test_cli_validate_invalid_rules_returns_nonzero_without_reading_mail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invalid_path = _write_rules(tmp_path / "invalid.toml", "[[rule]\n")
    monkeypatch.setattr(
        mail_triage,
        "iter_messages",
        lambda _profile: pytest.fail("mail must not be read"),
    )
    monkeypatch.setattr(
        mail_triage,
        "MailIndex",
        lambda _path: pytest.fail("index must not be opened"),
    )

    exit_code = mail_triage.main(["--validate-rules", "--rules", str(invalid_path)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Status: invalid" in captured.out
    assert "Error:" in captured.out
    assert captured.err == ""


def test_cli_invalid_rules_renders_fallback_without_mutating_index(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    messages = list(iter_messages(FIXTURE_ROOT))
    seeded = messages[0]
    index_path = tmp_path / "index.db"
    seeded_result = TriageResult(
        header_message_id=seeded.header_message_id,
        priority=Priority.URGENT,
        reason="Previously persisted personal result.",
        matched_rules=("personal:99",),
    )
    with MailIndex(index_path) as index:
        index.record_results([seeded], [seeded_result], processed_at=123.0)

    invalid_path = _write_rules(tmp_path / "invalid.toml", "unknown = true\n")
    exit_code = mail_triage.main(
        [
            "--profile",
            str(FIXTURE_ROOT),
            "--rules",
            str(invalid_path),
            "--index",
            str(index_path),
        ]
    )

    captured = capsys.readouterr()
    with sqlite3.connect(index_path) as conn:
        priority, processed_at = conn.execute(
            "SELECT priority, processed_at FROM processed_messages WHERE headerMessageID = ?",
            (seeded.header_message_id,),
        ).fetchone()
        last_run = conn.execute("SELECT last_run_ts FROM runs WHERE id = 1").fetchone()[0]
    assert exit_code != 0
    assert "MAIL-00 Digest" in captured.out
    assert "Personal rules disabled" in captured.err
    assert (priority, processed_at, last_run) == ("urgent", 123.0, 123.0)


def test_cli_persists_and_renders_the_same_effective_priority(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    index_path = tmp_path / "index.db"

    exit_code = mail_triage.main(
        [
            "--profile",
            str(FIXTURE_ROOT),
            "--rules",
            str(RULE_FIXTURE),
            "--index",
            str(index_path),
        ]
    )

    captured = capsys.readouterr()
    with MailIndex(index_path) as index:
        persisted = index.get_priority("important-1@example.test")
    assert exit_code == 0
    assert persisted == "urgent"
    assert "[urgent] Calendar invitation: project review" in captured.out
    assert "Fixture preferred sender." in captured.out
    assert captured.err == ""

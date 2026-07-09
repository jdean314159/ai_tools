from __future__ import annotations
# ruff: noqa: E402 -- exercise repository bootstrap before sibling-package imports

from dataclasses import replace
from pathlib import Path
import re
import sqlite3
import asyncio
from datetime import datetime, timedelta, timezone
import threading
import time
from typing import Iterable

import httpx
import pytest

from ._bootstrap import install_repo_source_paths

install_repo_source_paths()

from llm_engines import ChatMessage, GenerationResponse

from mail_lib.personal_rules import RuleAction, classify_message
from mail_lib.thunderbird import MailMessage, MessageMetadata
from mail_lib.triage import Priority

from .rules import RuleTransactionService
from .services import (
    SNAPSHOT_BODY_PREVIEW_CHARS,
    MailAssistantService,
    message_datetime,
)
from .store import AssistantStore
from .summarizer import PROMPT_VERSION, SectionSummarizer, section_key
from .web_app import AppConfig, _discover_thunderbird_profile, create_app
from .web_app import _run_blocking


def _message(
    message_id: str = "one@example.test",
    *,
    subject: str = "Fixture note",
    body: str = "Synthetic body",
    read: bool = False,
    date: str | None = None,
    folder_uri: str | None = None,
    sender: str = "sender@example.test",
    local_read: bool = False,
    read_state_source: str = "mbox",
) -> MailMessage:
    metadata = MessageMetadata(
        header_message_id=message_id,
        message_key=None,
        folder_id=None,
        conversation_id=None,
        date=None,
        sender_id=None,
        flags={"read": read},
        folder_uri=folder_uri,
    )
    return MailMessage(
        header_message_id=message_id,
        subject=subject,
        body=body,
        sender=sender,
        recipients=("user@example.test",),
        date=date,
        source_folder="INBOX",
        metadata=metadata,
        local_read=local_read,
        read_state_source=read_state_source,
    )


class FakeEngine:
    def __init__(self) -> None:
        self.calls = 0
        self.requests = []

    def generate(self, request):
        self.calls += 1
        self.requests.append(request)
        assert "untrusted data" in request.messages[0].content
        return GenerationResponse(
            message=ChatMessage(role="assistant", content="<script>summary</script>"),
            model_name="fixture",
            backend="mock",
        )


def test_store_is_app_owned_and_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "assistant.db"
    store = AssistantStore(path)
    AssistantStore(path)
    store.mark_read("one", read_at=1.0)
    store.put_summary("key", "model", "v1", "summary", created_at=2.0)

    assert store.read_ids() == {"one"}
    assert store.get_summary("key", "model", "v1") == "summary"
    with sqlite3.connect(path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
    assert {"read_state", "section_summary_cache"} <= tables
    assert "processed_messages" not in tables
    assert path.stat().st_mode & 0o777 == 0o600
    assert tmp_path.stat().st_mode & 0o777 == 0o700


def test_unread_state_merges_thunderbird_and_local_ledger(tmp_path: Path) -> None:
    messages = (
        _message("one"),
        _message("two", read=True),
        _message("three"),
        replace(_message("four", local_read=True), metadata=None),
        _message("five", read=False, local_read=True),
    )
    store = AssistantStore(tmp_path / "assistant.db")
    service = MailAssistantService(tmp_path, store, reader=lambda _path: messages)
    service.refresh()
    service.mark_read("three")

    unread = service.visible((), view="unread")
    all_messages = service.visible((), view="all")

    assert [
        item.message.header_message_id for values in unread.values() for item in values
    ] == ["one", "five"]
    assert sum(map(len, all_messages.values())) == 5
    with pytest.raises(KeyError):
        service.mark_read("unknown")


def test_msf_read_state_takes_precedence_over_gloda_and_cache(tmp_path: Path) -> None:
    messages = (
        _message(
            "one",
            read=True,
            local_read=False,
            read_state_source="msf",
        ),
        _message(
            "two",
            read=False,
            local_read=True,
            read_state_source="mbox",
        ),
    )
    store = AssistantStore(tmp_path / "assistant.db")
    service = MailAssistantService(tmp_path, store, reader=lambda _path: messages)
    service.refresh()
    reloaded = MailAssistantService(tmp_path, store, reader=lambda _path: ())
    reloaded.load_cached()

    unread = reloaded.visible((), view="unread")

    assert [
        item.message.header_message_id for values in unread.values() for item in values
    ] == ["one", "two"]


def test_failed_refresh_preserves_previous_snapshot(tmp_path: Path) -> None:
    calls = 0

    def reader(_path):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("fixture failure")
        return [_message()]

    service = MailAssistantService(tmp_path, AssistantStore(tmp_path / "a.db"), reader=reader)
    first = service.refresh()
    with pytest.raises(OSError):
        service.refresh()
    assert service.state == first


def test_refresh_passes_time_window_to_reader(tmp_path: Path) -> None:
    now = datetime(2026, 7, 9, 12, tzinfo=timezone.utc)
    seen_cutoffs: list[datetime] = []

    def reader(_path, *, newer_than=None):
        seen_cutoffs.append(newer_than)
        return [_message(date=now.isoformat())]

    service = MailAssistantService(
        tmp_path,
        AssistantStore(tmp_path / "windowed.db"),
        reader=reader,
    )

    state = service.refresh(max_age_days=7, now=now)

    assert seen_cutoffs == [now - timedelta(days=7)]
    assert state.max_age_days == 7
    assert state.message_count == 1
    assert state.refreshed_at is not None
    assert state.latest_message_at == now


def test_snapshot_cache_round_trips_messages_and_metadata(tmp_path: Path) -> None:
    store = AssistantStore(tmp_path / "a.db")
    original = _message(
        "cached", date="2026-07-05T12:00:00+00:00", local_read=True
    )
    writer = MailAssistantService(tmp_path, store, reader=lambda _path: [original])
    writer.refresh()
    reader = MailAssistantService(tmp_path, store, reader=lambda _path: [])

    loaded = reader.load_cached()

    assert loaded.messages == (original,)
    assert loaded.max_age_days is None
    assert loaded.message_count == 1
    assert loaded.refreshed_at is not None
    assert loaded.latest_message_at == datetime(2026, 7, 5, 12, tzinfo=timezone.utc)


def test_snapshot_cache_preserves_window_coverage(tmp_path: Path) -> None:
    store = AssistantStore(tmp_path / "windowed-cache.db")
    original = _message("cached", date="2026-07-05T12:00:00+00:00")
    writer = MailAssistantService(tmp_path, store, reader=lambda _path, **_kwargs: [original])
    writer.refresh(max_age_days=7, now=datetime(2026, 7, 9, tzinfo=timezone.utc))
    reader = MailAssistantService(tmp_path, store, reader=lambda _path, **_kwargs: [])

    loaded = reader.load_cached()

    assert loaded.messages == (original,)
    assert loaded.max_age_days == 7
    assert loaded.message_count == 1
    assert loaded.refreshed_at is not None
    assert loaded.latest_message_at == datetime(2026, 7, 5, 12, tzinfo=timezone.utc)


def test_refresh_stores_body_preview_and_hydrates_full_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from . import services as services_module

    full_body = "x" * (SNAPSHOT_BODY_PREVIEW_CHARS + 25)
    mbox_path = tmp_path / "INBOX"
    original = replace(_message("full@example.test", body=full_body), mbox_path=mbox_path)
    store = AssistantStore(tmp_path / "preview.db")
    service = MailAssistantService(tmp_path, store, reader=lambda _path, **_kwargs: [original])
    monkeypatch.setattr(
        services_module,
        "load_message_body",
        lambda path, message_id: full_body
        if path == mbox_path and message_id == "full@example.test"
        else "",
    )

    refreshed = service.refresh()
    reloaded = MailAssistantService(tmp_path, store, reader=lambda _path, **_kwargs: [])
    cached = reloaded.load_cached()

    assert len(refreshed.messages[0].body) == SNAPSHOT_BODY_PREVIEW_CHARS
    assert refreshed.messages[0].body == full_body[:SNAPSHOT_BODY_PREVIEW_CHARS]
    assert refreshed.messages[0].body_complete is False
    assert cached.messages[0].body == full_body[:SNAPSHOT_BODY_PREVIEW_CHARS]
    assert cached.messages[0].body_complete is False
    hydrated = service.full_message("full@example.test")
    assert hydrated.body == full_body
    assert hydrated.body_complete is True


def test_full_messages_hydrates_by_mbox_in_batches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from . import services as services_module

    mbox_path = tmp_path / "INBOX"
    messages = (
        replace(
            _message("first@example.test", body="first-preview"),
            mbox_path=mbox_path,
            body_complete=False,
        ),
        replace(
            _message("second@example.test", body="second-preview"),
            mbox_path=mbox_path,
            body_complete=False,
        ),
    )
    service = MailAssistantService(
        tmp_path,
        AssistantStore(tmp_path / "batch.db"),
        reader=lambda _path, **_kwargs: messages,
    )
    service.refresh()
    calls: list[tuple[Path, tuple[str, ...]]] = []

    def fake_load_message_bodies(path: Path, message_ids: Iterable[str]) -> dict[str, str]:
        requested = tuple(message_ids)
        calls.append((path, requested))
        return {
            "first@example.test": "first-full",
            "second@example.test": "second-full",
        }

    monkeypatch.setattr(services_module, "load_message_bodies", fake_load_message_bodies)

    hydrated = service.full_messages(("second@example.test", "first@example.test"))

    assert [message.body for message in hydrated] == ["second-full", "first-full"]
    assert all(message.body_complete for message in hydrated)
    assert calls == [
        (
            mbox_path,
            ("second@example.test", "first@example.test"),
        )
    ]


def test_messages_are_newest_first_and_filtered_by_age(tmp_path: Path) -> None:
    now = datetime(2026, 7, 5, 12, tzinfo=timezone.utc)
    messages = (
        _message("old", date=(now - timedelta(days=40)).isoformat()),
        _message("newest", date=(now - timedelta(hours=1)).isoformat()),
        _message("middle", date=(now - timedelta(days=5)).isoformat()),
        _message("undated"),
    )
    service = MailAssistantService(
        tmp_path,
        AssistantStore(tmp_path / "a.db"),
        reader=lambda _path: messages,
    )
    service.refresh()

    all_groups = service.visible((), view="all", now=now)
    windowed_groups = service.visible((), view="all", max_age_days=14, now=now)
    all_ids = {item.message.header_message_id for group in all_groups.values() for item in group}
    windowed_ids = [
        item.message.header_message_id for group in windowed_groups.values() for item in group
    ]

    assert all_ids == {"newest", "middle", "old", "undated"}
    assert set(windowed_ids) == {"newest", "middle"}
    for group in all_groups.values():
        dated = [message_datetime(item.message) for item in group]
        assert dated == sorted(
            dated,
            key=lambda value: value or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )


def test_sender_and_domain_volume_stats_share_window_and_unread_state(tmp_path: Path) -> None:
    now = datetime(2026, 7, 6, 12, tzinfo=timezone.utc)
    messages = (
        _message("a1", sender="A@example.test", date=(now - timedelta(days=1)).isoformat()),
        _message("a2", sender="a@example.test", date=(now - timedelta(days=2)).isoformat()),
        _message("b1", sender="b@example.test", date=(now - timedelta(days=3)).isoformat(), read=True),
        _message("old", sender="a@example.test", date=(now - timedelta(days=20)).isoformat()),
        _message("undated", sender="c@other.test"),
    )
    store = AssistantStore(tmp_path / "stats.db")
    store.mark_read("a2")
    service = MailAssistantService(tmp_path, store, reader=lambda _path: messages)
    service.refresh()

    senders, domains = service.volume_stats(max_age_days=7, now=now)

    assert [(row.value, row.count, row.unread_count) for row in senders] == [
        ("a@example.test", 2, 1),
        ("b@example.test", 1, 0),
    ]
    assert senders[0].share == pytest.approx(2 / 3)
    assert senders[0].most_recent == now - timedelta(days=1)
    assert [(row.value, row.count, row.unread_count) for row in domains] == [
        ("example.test", 3, 1)
    ]
    empty_senders, empty_domains = service.volume_stats(max_age_days=1, now=now + timedelta(days=30))
    assert empty_senders == () and empty_domains == ()


def test_visible_filters_before_classification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from . import services as services_module

    now = datetime(2026, 7, 6, 12, tzinfo=timezone.utc)
    messages = (
        _message("old", date=(now - timedelta(days=30)).isoformat()),
        _message("read", date=now.isoformat(), read=True),
        _message("visible", date=now.isoformat()),
    )
    service = MailAssistantService(
        tmp_path,
        AssistantStore(tmp_path / "filter.db"),
        reader=lambda _path: messages,
    )
    service.refresh()
    classified_ids = []
    original = services_module.classify_message

    def tracked(message, rules):
        classified_ids.append(message.header_message_id)
        return original(message, rules)

    monkeypatch.setattr(services_module, "classify_message", tracked)

    service.visible((), view="unread", max_age_days=7, now=now)

    assert classified_ids == ["visible"]


def test_summary_cache_varies_with_exact_content_model_and_prompt(tmp_path: Path) -> None:
    store = AssistantStore(tmp_path / "a.db")
    engine = FakeEngine()
    first = [classify_message(_message(body="first"), ())]
    changed = [classify_message(_message(body="changed"), ())]
    summarizer = SectionSummarizer(engine, store, model="fixture")

    assert summarizer.summarize(first) == "<script>summary</script>"
    assert summarizer.summarize(first) == "<script>summary</script>"
    assert summarizer.summarize(changed) == "<script>summary</script>"
    assert engine.calls == 2
    assert section_key(first) != section_key(changed)
    assert store.get_summary(section_key(first), "fixture", PROMPT_VERSION)


def test_summarize_hydrates_full_body_before_model_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from . import services as services_module

    full_body = "x" * SNAPSHOT_BODY_PREVIEW_CHARS + "FULL_TAIL"
    mbox_path = tmp_path / "INBOX"
    message = replace(
        _message("summary-full@example.test", body=full_body, date=datetime.now(timezone.utc).isoformat()),
        mbox_path=mbox_path,
    )
    monkeypatch.setattr(
        services_module,
        "load_message_bodies",
        lambda path, message_ids: {"summary-full@example.test": full_body}
        if path == mbox_path and tuple(message_ids) == ("summary-full@example.test",)
        else {},
    )
    app = _web_app(tmp_path)
    app.state.mail._reader = lambda _path, **_kwargs: [message]
    app.state.mail.refresh()

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/summarize/normal",
                data={
                    "csrf_token": app.state.csrf_token,
                    "view": "all",
                    "window_value": 1,
                    "window_unit": "weeks",
                },
            )
            assert response.status_code == 200
            prompt = app.state.test_engine.requests[-1].messages[1].content
            assert "FULL_TAIL" in prompt

    asyncio.run(exercise())


def test_summarizer_rejects_one_oversized_message(tmp_path: Path) -> None:
    summarizer = SectionSummarizer(FakeEngine(), AssistantStore(tmp_path / "a.db"), model="m", input_budget=1)
    with pytest.raises(ValueError, match="headers exceed"):
        summarizer.summarize([classify_message(_message(body="too long"), ())])


def test_summarizer_allocates_budget_across_every_message(tmp_path: Path) -> None:
    class CharacterCountingEngine(FakeEngine):
        @staticmethod
        def count_tokens(text: str) -> int:
            return len(text)

    engine = CharacterCountingEngine()
    messages = [
        classify_message(_message(f"message-{index}", body=str(index) * 1_000), ())
        for index in range(3)
    ]
    summarizer = SectionSummarizer(
        engine,
        AssistantStore(tmp_path / "a.db"),
        model="m",
        input_budget=1_000,
        output_tokens=100,
    )

    summarizer.summarize(messages)

    prompt = engine.requests[0].messages[1].content
    assert all(f"message-{index}" in prompt for index in range(3))
    assert prompt.count('"body_truncated": true') == 3
    assert "Summarize all 3 messages" in prompt
    assert "Sender: ...\nSubject: ...\nKey point: ...\nRequested action: ...\nDeadline: ..." in prompt
    assert engine.requests[0].max_tokens == 360


def test_rule_propose_commit_is_derived_atomic_and_one_shot(tmp_path: Path) -> None:
    rules_path = tmp_path / "personal_rules.toml"
    rules_path.write_text("", encoding="utf-8")
    service = RuleTransactionService(rules_path)

    proposal = service.propose(
        _message(), field="sender", priority=Priority.URGENT, action=RuleAction.SUMMARIZE
    )
    assert rules_path.read_text() == ""
    assert 'sender = "sender@example.test"' in proposal.diff
    loaded = service.commit(proposal.token)
    assert loaded.ok and loaded.rules[0].action == RuleAction.SUMMARIZE
    assert rules_path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="already-used"):
        service.commit(proposal.token)


def test_stats_match_value_produces_same_rule_proposal_as_message(tmp_path: Path) -> None:
    service = RuleTransactionService(tmp_path / "rules.toml")
    message = _message(sender="volume@example.test")

    from_message = service.propose(
        message, field="sender", priority=Priority.LOW, action=RuleAction.NONE
    )
    from_stats = service.propose(
        None,
        field="sender",
        match_value="volume@example.test",
        priority=Priority.LOW,
        action=RuleAction.NONE,
    )

    assert from_stats.diff == from_message.diff
    assert from_stats.candidate_sha256 == from_message.candidate_sha256


def test_rule_commit_preserves_existing_comments_and_formatting(tmp_path: Path) -> None:
    rules_path = tmp_path / "personal_rules.toml"
    original = (
        b"# Hand-maintained rules\n"
        b"[[rule]] # keep this inline comment\n"
        b"priority='low' # keep priority comment\n"
        b"sender = 'sender@example.test'\n"
        b"action = 'none' # keep action comment\n"
    )
    rules_path.write_bytes(original)
    service = RuleTransactionService(rules_path)

    proposal = service.propose(
        _message(), field="sender", priority=Priority.URGENT, action=RuleAction.SUMMARIZE
    )
    assert proposal.validation.ok
    assert proposal.validation.warnings == ()
    service.commit(proposal.token)

    committed = rules_path.read_bytes()
    assert committed.count(b"[[rule]]") == 1
    assert committed.count(b"# Hand-maintained rules") == 1
    assert b"sender = 'sender@example.test'" in committed
    assert b'priority="urgent" # keep priority comment' in committed
    assert b'action = "summarize" # keep action comment' in committed


def test_rule_append_separates_file_without_trailing_newline(tmp_path: Path) -> None:
    rules_path = tmp_path / "personal_rules.toml"
    original = (
        b"[[rule]]\n"
        b"sender = 'existing@example.test'\n"
        b"priority = 'low'\n"
        b"action = 'none'"
    )
    rules_path.write_bytes(original)
    service = RuleTransactionService(rules_path)

    proposal = service.propose(
        _message(), field="subject", priority=Priority.NORMAL, action=RuleAction.NONE
    )
    service.commit(proposal.token)

    assert rules_path.read_bytes().startswith(original + b"\n\n[[rule]]\n")


def test_rule_upsert_adds_missing_action_without_appending_duplicate(tmp_path: Path) -> None:
    rules_path = tmp_path / "personal_rules.toml"
    rules_path.write_bytes(
        b"[[rule]]\nsender = 'sender@example.test'\npriority = 'urgent'"
    )
    service = RuleTransactionService(rules_path)

    proposal = service.propose(
        _message(), field="sender", priority=Priority.LOW, action=RuleAction.IGNORE
    )
    service.commit(proposal.token)

    committed = rules_path.read_bytes()
    assert committed.count(b"[[rule]]") == 1
    assert b'priority = "low"' in committed
    assert b'action = "ignore"' in committed


def test_rule_commit_rejects_external_change_and_symlink(tmp_path: Path) -> None:
    rules_path = tmp_path / "personal_rules.toml"
    rules_path.write_text("", encoding="utf-8")
    service = RuleTransactionService(rules_path)
    proposal = service.propose(
        _message(), field="subject", priority=Priority.LOW, action=RuleAction.NONE
    )
    rules_path.write_text("# external edit\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="changed after proposal"):
        service.commit(proposal.token)
    assert rules_path.read_text() == "# external edit\n"

    target = tmp_path / "target.toml"
    target.write_text("", encoding="utf-8")
    link = tmp_path / "linked.toml"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        RuleTransactionService(link).propose(
            _message(), field="sender", priority=Priority.LOW, action=RuleAction.IGNORE
        )


def test_atomic_replace_failure_preserves_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rules_path = tmp_path / "personal_rules.toml"
    original = b"# original\n"
    rules_path.write_bytes(original)
    service = RuleTransactionService(rules_path)
    proposal = service.propose(
        _message(), field="sender", priority=Priority.LOW, action=RuleAction.NONE
    )
    monkeypatch.setattr("examples.mail_assistant.rules.os.replace", lambda *_args: (_ for _ in ()).throw(OSError("replace failed")))

    with pytest.raises(OSError, match="replace failed"):
        service.commit(proposal.token)
    assert rules_path.read_bytes() == original


def test_proposal_refuses_to_rewrite_invalid_existing_rules(tmp_path: Path) -> None:
    rules_path = tmp_path / "personal_rules.toml"
    invalid = b"[[rule]\n"
    rules_path.write_bytes(invalid)

    with pytest.raises(ValueError, match="Existing personal rules are invalid"):
        RuleTransactionService(rules_path).propose(
            _message(), field="sender", priority=Priority.LOW, action=RuleAction.NONE
        )
    assert rules_path.read_bytes() == invalid


def test_blocking_runner_enforces_timeout() -> None:
    async def exercise() -> None:
        with pytest.raises(TimeoutError):
            await _run_blocking(time.sleep, 0.1, timeout=0.01)

    asyncio.run(exercise())


def _web_app(
    tmp_path: Path,
    message: MailMessage | None = None,
    *,
    imap_accounts_path: Path | None = None,
):
    config = AppConfig(
        profile=tmp_path,
        rules_path=tmp_path / "rules.toml",
        database_path=tmp_path / "web.db",
        model="fixture",
        imap_accounts_path=imap_accounts_path,
    )
    test_engine = FakeEngine()
    app = create_app(config, engine=test_engine)
    app.state.test_engine = test_engine
    app.state.mail._reader = lambda _path, **_kwargs: [message or _message()]
    return app


def test_web_security_headers_host_and_csrf_token(tmp_path: Path) -> None:
    app = _web_app(tmp_path)
    app.state.mail.refresh()

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/")
            assert response.status_code == 200
            assert "default-src 'self'" in response.headers["content-security-policy"]
            assert "Snapshot:" in response.text
            assert "Snapshot covers the selected window." in response.text
            assert 'name="window_value" min="1" max="3650" value="1"' in response.text
            assert '<option value="weeks" selected>weeks</option>' in response.text
            assert (await client.get("/", headers={"host": "attacker.test"})).status_code == 400

            form = {"message_id": "one@example.test", "csrf_token": "wrong", "view": "unread"}
            assert (await client.post("/read", data=form, headers={"origin": "http://testserver"})).status_code == 403
            form["csrf_token"] = app.state.csrf_token
            assert (await client.post("/read", data=form)).status_code == 200
            assert (await client.post(
                "/read", data=form, headers={"origin": "http://testserver"}
            )).status_code == 200
            assert (await client.post(
                "/read", data=form, headers={"origin": "http://attacker.test"}
            )).status_code == 403
            assert (await client.post(
                "/read", data=form, headers={"origin": "null"}
            )).status_code == 200
            assert (await client.post(
                "/read", data=form, headers={"sec-fetch-site": "same-origin"}
            )).status_code == 200
            assert (await client.post(
                "/read", data=form, headers={"sec-fetch-site": "cross-site"}
            )).status_code == 200

    asyncio.run(exercise())


def test_stats_route_and_exact_sender_filter(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    messages = [
        _message("stats-a@example.test", subject="From A", sender="a@example.test", date=now),
        _message("stats-b@example.test", subject="From B", sender="b@example.test", date=now),
    ]
    app = _web_app(tmp_path)
    app.state.mail._reader = lambda _path: messages
    app.state.mail.refresh()

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            stats = await client.get("/stats")
            assert stats.status_code == 200
            assert "Snapshot:" in stats.text
            assert "a@example.test" in stats.text
            assert "b@example.test" in stats.text
            filtered = await client.get(
                "/",
                params={"view": "all", "sender": "a@example.test"},
            )
            assert "From A" in filtered.text
            assert "From B" not in filtered.text
            summary = await client.post(
                "/summarize/normal",
                data={
                    "csrf_token": app.state.csrf_token,
                    "view": "all",
                    "window_value": 1,
                    "window_unit": "weeks",
                    "sender_filter": "a@example.test",
                    "domain_filter": "",
                },
            )
            assert summary.status_code == 200
            prompt = app.state.test_engine.requests[-1].messages[1].content
            assert "a@example.test" in prompt
            assert "b@example.test" not in prompt
            marked = await client.post(
                "/read",
                data={
                    "message_id": "stats-a@example.test",
                    "csrf_token": app.state.csrf_token,
                    "view": "all",
                    "window_value": 1,
                    "window_unit": "weeks",
                    "sender_filter": "a@example.test",
                    "domain_filter": "",
                },
            )
            assert marked.status_code == 200
            assert "From A" in marked.text
            assert "From B" not in marked.text

    asyncio.run(exercise())


def test_list_render_limit_caps_cards_without_changing_section_count(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    messages = [_message(f"limit-{index}", date=now) for index in range(60)]
    app = _web_app(tmp_path)
    app.state.mail._reader = lambda _path: messages
    app.state.mail.refresh()

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            page = await client.get("/", params={"view": "all", "limit": 10})
            assert page.status_code == 200
            assert "normal (60)" in page.text
            assert "Showing the newest 10 of 60" in page.text
            assert page.text.count('<article class="message">') == 10

    asyncio.run(exercise())


def test_summary_budget_failure_renders_visible_fragment(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    messages = [
        _message(
            f"oversized-{index}",
            subject=f"Fixture {index} " + "x " * 2_000,
            date=now,
        )
        for index in range(20)
    ]
    app = _web_app(tmp_path)
    app.state.mail._reader = lambda _path: messages
    app.state.mail.refresh()

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/summarize/normal",
                data={
                    "csrf_token": app.state.csrf_token,
                    "view": "all",
                    "summary_limit": 20,
                },
            )
            assert response.status_code == 200
            assert "Summary unavailable" in response.text
            assert "headers exceed" in response.text

    asyncio.run(exercise())


def test_app_lifespan_loads_initial_snapshot(tmp_path: Path) -> None:
    app = _web_app(tmp_path)

    async def exercise() -> None:
        assert app.state.mail.state.revision == 0
        async with app.router.lifespan_context(app):
            await app.state.refresh_task
            assert app.state.mail.state.revision == 1
            assert len(app.state.mail.state.messages) == 1

    asyncio.run(exercise())


def test_default_thunderbird_profile_discovery(tmp_path: Path) -> None:
    selected = tmp_path / "chosen.default"
    selected.mkdir()
    (tmp_path / "other.default").mkdir()
    (tmp_path / "profiles.ini").write_text(
        "[Profile1]\nName=other\nIsRelative=1\nPath=other.default\n\n"
        "[Profile0]\nName=chosen\nIsRelative=1\nPath=chosen.default\nDefault=1\n",
        encoding="utf-8",
    )

    assert _discover_thunderbird_profile(tmp_path) == selected


def test_default_thunderbird_profile_discovery_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="set MAIL_ASSISTANT_PROFILE"):
        _discover_thunderbird_profile(tmp_path)


def test_refresh_route_runs_mailbox_scan_off_event_loop(tmp_path: Path) -> None:
    app = _web_app(tmp_path)
    original_refresh = app.state.mail.refresh
    worker_threads: list[int] = []
    refresh_windows: list[int | None] = []

    def tracked_refresh(*, max_age_days=None):
        worker_threads.append(threading.get_ident())
        refresh_windows.append(max_age_days)
        return original_refresh(max_age_days=max_age_days)

    app.state.mail.refresh = tracked_refresh

    async def exercise() -> None:
        event_loop_thread = threading.get_ident()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/refresh",
                data={"csrf_token": app.state.csrf_token, "view": "unread"},
            )
            await app.state.refresh_task
            completed = await client.get("/refresh-status")
        assert response.status_code == 303
        assert response.headers["location"] == "/?view=unread&window_value=1&window_unit=weeks"
        assert completed.status_code == 204
        assert completed.headers["hx-refresh"] == "true"
        assert worker_threads and worker_threads[0] != event_loop_thread
        assert refresh_windows == [7]

    asyncio.run(exercise())


def test_wider_refresh_request_is_not_lost_while_refresh_runs(tmp_path: Path) -> None:
    app = _web_app(tmp_path)
    calls: list[int | None] = []
    first_started = threading.Event()
    release_first = threading.Event()

    def tracked_refresh(*, max_age_days=None):
        calls.append(max_age_days)
        if len(calls) == 1:
            first_started.set()
            assert release_first.wait(timeout=5)
        return app.state.mail.__class__.refresh(
            app.state.mail,
            max_age_days=max_age_days,
        )

    app.state.mail.refresh = tracked_refresh

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            first = await client.post(
                "/refresh",
                data={
                    "csrf_token": app.state.csrf_token,
                    "view": "unread",
                    "window_value": 1,
                    "window_unit": "weeks",
                },
            )
            assert first.status_code == 303
            assert first_started.wait(timeout=5)
            second = await client.post(
                "/refresh",
                data={
                    "csrf_token": app.state.csrf_token,
                    "view": "unread",
                    "window_value": 4,
                    "window_unit": "weeks",
                },
            )
            assert second.status_code == 303
            release_first.set()
            await app.state.refresh_task

    asyncio.run(exercise())

    assert calls == [7, 28]
    assert app.state.mail.state.max_age_days == 28


def test_rule_preview_targets_selected_message_row(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    first = _message("first", subject="First unique subject", date=now)
    second = _message("second", subject="Second unique subject", date=now)
    app = _web_app(tmp_path)
    app.state.mail._reader = lambda _path: [first, second]
    app.state.mail.refresh()

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            page = await client.get("/?view=all")
            assert page.text.count('id="proposal-normal-visible-') == 2
            assert 'hx-target="#proposal-normal-visible-1"' in page.text
            assert 'hx-target="#proposal-normal-visible-2"' in page.text

            preview = await client.post(
                "/rules/propose",
                data={
                    "message_id": "second",
                    "field": "subject",
                    "priority": "low",
                    "action": "none",
                    "csrf_token": app.state.csrf_token,
                    "view": "all",
                    "window_value": 1,
                    "window_unit": "weeks",
                },
            )
            assert preview.status_code == 200
            assert "second unique subject" in preview.text
            assert "first unique subject" not in preview.text
            assert "This rule has not been applied yet." in preview.text

    asyncio.run(exercise())


def test_trash_requires_preview_then_removes_only_after_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "imap.toml"
    config_path.write_text(
        "[[account]]\nhost='imap.example.test'\nusername='user@example.test'\n"
        "password_env='TEST_IMAP_PASSWORD'\ntrash_folder='Trash'\n",
        encoding="utf-8",
    )
    first = _message(
        "first-trash@example.test",
        subject="First trash subject",
        date=datetime.now(timezone.utc).isoformat(),
        folder_uri="imap://user%40example.test@imap.example.test/INBOX",
    )
    second = _message(
        "second-trash@example.test",
        subject="Second trash subject",
        date=datetime.now(timezone.utc).isoformat(),
        folder_uri="imap://user%40example.test@imap.example.test/INBOX",
    )
    app = _web_app(tmp_path, first, imap_accounts_path=config_path)
    app.state.mail._reader = lambda _path: [first, second]
    app.state.mail.refresh()
    moved = []

    def move(selected_messages, _accounts, *, prefs_cache=None):
        result = {}
        for selected in selected_messages:
            if selected.header_message_id == second.header_message_id:
                result[selected.header_message_id] = "injected failure"
                continue
            moved.append(selected.header_message_id)
            result[selected.header_message_id] = None
        return result

    monkeypatch.setattr(
        "examples.mail_assistant.trash_workflow.move_messages_to_trash",
        move,
    )
    monkeypatch.setattr(
        "examples.mail_assistant.trash_workflow.verify_messages_available_for_move",
        lambda _messages, _accounts, *, prefs_cache=None: None,
    )

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            page = await client.get("/")
            assert "Review selected for Trash…" in page.text
            assert 'class="select-trash-visible"' in page.text
            assert 'data-trash-group="normal-visible"' in page.text
            assert "Select all 2 eligible visible in normal for Trash" in page.text
            assert "Trash target: user@example.test INBOX → Trash" in page.text
            preview = await client.post(
                "/trash/propose",
                data={
                    "message_ids": [first.header_message_id, second.header_message_id],
                    "csrf_token": app.state.csrf_token,
                },
            )
            assert preview.status_code == 200
            assert "First trash subject" in preview.text
            assert "Second trash subject" in preview.text
            assert moved == []
            token = re.search(r'name="trash_token" value="([^"]+)"', preview.text)
            assert token is not None
            committed = await client.post(
                "/trash/commit",
                data={
                    "trash_token": token.group(1),
                    "csrf_token": app.state.csrf_token,
                },
            )
            assert committed.status_code == 200
            assert "1 moved, 1 failed, 0 skipped" in committed.text
            assert "injected failure" in committed.text
            assert moved == [first.header_message_id]
            assert [item.header_message_id for item in app.state.mail.state.messages] == [
                second.header_message_id
            ]
            replay = await client.post(
                "/trash/commit",
                data={
                    "trash_token": token.group(1),
                    "csrf_token": app.state.csrf_token,
                },
            )
            assert replay.status_code == 400
            monkeypatch.setattr(
                "examples.mail_assistant.trash_workflow.time.time", lambda: 1_000.0
            )
            expiring = await client.post(
                "/trash/propose",
                data={
                    "message_ids": second.header_message_id,
                    "csrf_token": app.state.csrf_token,
                },
            )
            expiring_token = re.search(
                r'name="trash_token" value="([^"]+)"', expiring.text
            )
            assert expiring_token is not None
            monkeypatch.setattr(
                "examples.mail_assistant.trash_workflow.time.time", lambda: 2_000.0
            )
            expired = await client.post(
                "/trash/commit",
                data={
                    "trash_token": expiring_token.group(1),
                    "csrf_token": app.state.csrf_token,
                },
            )
            assert expired.status_code == 400

    asyncio.run(exercise())


def test_configured_trash_messages_are_excluded_from_refresh_and_cache(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "imap.toml"
    config_path.write_text(
        "[[account]]\nhost='imap.example.test'\nusername='user@example.test'\n"
        "password_env='TEST_IMAP_PASSWORD'\ntrash_folder='[Gmail]/Trash'\n",
        encoding="utf-8",
    )
    inbox = _message(
        "inbox@example.test",
        subject="Visible inbox message",
        sender="visible@example.test",
        date=datetime.now(timezone.utc).isoformat(),
        folder_uri="imap://user%40example.test@imap.example.test/INBOX",
    )
    trashed = _message(
        "trashed@example.test",
        subject="Ignored trash message",
        sender="ignored@example.test",
        date=datetime.now(timezone.utc).isoformat(),
        folder_uri="imap://user%40example.test@imap.example.test/INBOX",
    )
    trashed = replace(trashed, signal_folders=("[Gmail]/Trash",))
    app = _web_app(tmp_path, inbox, imap_accounts_path=config_path)
    app.state.mail._reader = lambda _path: [inbox, trashed]
    app.state.mail.refresh()

    assert [item.header_message_id for item in app.state.mail.state.messages] == [
        inbox.header_message_id
    ]
    senders, _domains = app.state.mail.volume_stats(max_age_days=7)
    assert [item.value for item in senders] == ["visible@example.test"]

    cached_app = _web_app(tmp_path, inbox, imap_accounts_path=config_path)
    cached_app.state.mail.load_cached()
    assert [
        item.header_message_id for item in cached_app.state.mail.state.messages
    ] == [inbox.header_message_id]


def test_batch_trash_proposal_rejects_any_unsafe_or_unmapped_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "imap.toml"
    config_path.write_text(
        "[[account]]\nhost='imap.example.test'\nusername='user@example.test'\n"
        "password_env='TEST_IMAP_PASSWORD'\ntrash_folder='Trash'\n",
        encoding="utf-8",
    )
    now = datetime.now(timezone.utc).isoformat()
    good = _message(
        "good@example.test",
        date=now,
        folder_uri="imap://user%40example.test@imap.example.test/INBOX",
    )
    hostile = _message(
        "hostile@example.test\r\nEXPUNGE",
        date=now,
        folder_uri="imap://user%40example.test@imap.example.test/INBOX",
    )
    unmapped = _message(
        "unmapped@example.test",
        date=now,
        folder_uri="imap://user%40example.test@other.example.test/INBOX",
    )
    app = _web_app(tmp_path, good, imap_accounts_path=config_path)
    monkeypatch.setattr(
        "examples.mail_assistant.trash_workflow.verify_messages_available_for_move",
        lambda _messages, _accounts, *, prefs_cache=None: None,
    )

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            for rejected in (hostile, unmapped):
                app.state.mail._reader = lambda _path, item=rejected: [good, item]
                app.state.mail.refresh()
                page = await client.get("/?view=all")
                assert page.status_code == 200
                assert page.text.count('name="message_ids"') == 1
                assert "Trash unavailable:" in page.text
                response = await client.post(
                    "/trash/propose",
                    data={
                        "message_ids": [good.header_message_id, rejected.header_message_id],
                        "csrf_token": app.state.csrf_token,
                    },
                )
                assert response.status_code == 400
                assert response.headers["content-type"].startswith("text/html")
                assert "No messages were moved." in response.text

    asyncio.run(exercise())


def test_batch_trash_proposal_rejects_message_missing_from_imap_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "imap.toml"
    config_path.write_text(
        "[[account]]\nhost='imap.example.test'\nusername='user@example.test'\n"
        "password_env='TEST_IMAP_PASSWORD'\ntrash_folder='Trash'\n",
        encoding="utf-8",
    )
    stale = _message(
        "stale@example.test",
        subject="Stale local cache row",
        date=datetime.now(timezone.utc).isoformat(),
        folder_uri="imap://user%40example.test@imap.example.test/INBOX",
    )
    app = _web_app(tmp_path, stale, imap_accounts_path=config_path)
    app.state.mail.refresh()

    def missing_from_server(_messages, _accounts, *, prefs_cache=None):
        raise RuntimeError("Message was not found on the IMAP server")

    monkeypatch.setattr(
        "examples.mail_assistant.trash_workflow.verify_messages_available_for_move",
        missing_from_server,
    )

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/trash/propose",
                data={
                    "message_ids": [stale.header_message_id],
                    "csrf_token": app.state.csrf_token,
                },
            )
            assert response.status_code == 400
            assert "No messages were moved." in response.text
            assert "Message was not found on the IMAP server" in response.text
            assert "trash_token" not in response.text

    asyncio.run(exercise())


def test_batch_trash_commit_skips_message_that_left_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "imap.toml"
    config_path.write_text(
        "[[account]]\nhost='imap.example.test'\nusername='user@example.test'\n"
        "password_env='TEST_IMAP_PASSWORD'\ntrash_folder='Trash'\n",
        encoding="utf-8",
    )
    messages = [
        _message(
            f"skip-{index}@example.test",
            subject=f"Skip fixture {index}",
            folder_uri="imap://user%40example.test@imap.example.test/INBOX",
        )
        for index in range(2)
    ]
    app = _web_app(tmp_path, messages[0], imap_accounts_path=config_path)
    app.state.mail._reader = lambda _path: messages
    app.state.mail.refresh()
    moved = []
    monkeypatch.setattr(
        "examples.mail_assistant.trash_workflow.move_messages_to_trash",
        lambda messages, _accounts, *, prefs_cache=None: {
            message.header_message_id: (
                moved.append(message.header_message_id) and None
            )
            for message in messages
        },
    )
    monkeypatch.setattr(
        "examples.mail_assistant.trash_workflow.verify_messages_available_for_move",
        lambda _messages, _accounts, *, prefs_cache=None: None,
    )

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            preview = await client.post(
                "/trash/propose",
                data={
                    "message_ids": [item.header_message_id for item in messages],
                    "csrf_token": app.state.csrf_token,
                },
            )
            assert preview.status_code == 200
            token = re.search(r'name="trash_token" value="([^"]+)"', preview.text)
            assert token is not None

            app.state.mail.remove_message(messages[1].header_message_id)
            committed = await client.post(
                "/trash/commit",
                data={
                    "trash_token": token.group(1),
                    "csrf_token": app.state.csrf_token,
                },
            )

            assert committed.status_code == 200
            assert "1 moved, 0 failed, 1 skipped" in committed.text
            assert "Message left the snapshot before confirmation." in committed.text
            assert moved == [messages[0].header_message_id]

    asyncio.run(exercise())


def test_web_escapes_mail_and_model_output(tmp_path: Path) -> None:
    malicious = _message(
        subject="<script>alert(1)</script>",
        body="<img src=x onerror=alert(2)>",
        date=datetime.now(timezone.utc).isoformat(),
    )
    app = _web_app(tmp_path, malicious)
    app.state.mail.refresh()
    headers = {"origin": "http://testserver"}

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            page = await client.get("/")
            assert "<script>alert(1)</script>" not in page.text
            assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text
            detail = await client.get(
                "/message", params={"message_id": malicious.header_message_id}
            )
            assert detail.status_code == 200
            assert "<script>alert(1)</script>" not in detail.text
            assert "&lt;script&gt;alert(1)&lt;/script&gt;" in detail.text
            assert "<img src=x onerror=alert(2)>" not in detail.text
            assert "&lt;img src=x onerror=alert(2)&gt;" in detail.text
            assert (
                await client.get("/message", params={"message_id": "missing"})
            ).status_code == 404
            response = await client.post(
                "/summarize/normal",
                data={"csrf_token": app.state.csrf_token, "view": "unread"},
                headers=headers,
            )
            assert response.status_code == 200
            assert "<script>summary</script>" not in response.text
            assert "&lt;script&gt;summary&lt;/script&gt;" in response.text

    asyncio.run(exercise())

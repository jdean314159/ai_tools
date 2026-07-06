from __future__ import annotations
# ruff: noqa: E402 -- exercise repository bootstrap before sibling-package imports

from pathlib import Path
import re
import sqlite3
import asyncio
from datetime import datetime, timedelta, timezone
import threading
import time

import httpx
import pytest

from ._bootstrap import install_repo_source_paths

install_repo_source_paths()

from llm_engines import ChatMessage, GenerationResponse

from mail_lib.personal_rules import RuleAction, classify_message
from mail_lib.thunderbird import MailMessage, MessageMetadata
from mail_lib.triage import Priority

from .rules import RuleTransactionService
from .services import MailAssistantService, message_datetime
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
        sender="sender@example.test",
        recipients=("user@example.test",),
        date=date,
        source_folder="INBOX",
        metadata=metadata,
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
    messages = (_message("one"), _message("two", read=True), _message("three"))
    store = AssistantStore(tmp_path / "assistant.db")
    service = MailAssistantService(tmp_path, store, reader=lambda _path: messages)
    service.refresh()
    service.mark_read("three")

    unread = service.visible((), view="unread")
    all_messages = service.visible((), view="all")

    assert [item.message.header_message_id for values in unread.values() for item in values] == ["one"]
    assert sum(map(len, all_messages.values())) == 3
    with pytest.raises(KeyError):
        service.mark_read("unknown")


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


def test_snapshot_cache_round_trips_messages_and_metadata(tmp_path: Path) -> None:
    store = AssistantStore(tmp_path / "a.db")
    original = _message("cached", date="2026-07-05T12:00:00+00:00")
    writer = MailAssistantService(tmp_path, store, reader=lambda _path: [original])
    writer.refresh()
    reader = MailAssistantService(tmp_path, store, reader=lambda _path: [])

    loaded = reader.load_cached()

    assert loaded.messages == (original,)


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
    )

    summarizer.summarize(messages)

    prompt = engine.requests[0].messages[1].content
    assert all(f"message-{index}" in prompt for index in range(3))
    assert prompt.count('"body_truncated": true') == 3
    assert "Summarize all 3 messages" in prompt


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
    app = create_app(config, engine=FakeEngine())
    app.state.mail._reader = lambda _path: [message or _message()]
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

    def tracked_refresh():
        worker_threads.append(threading.get_ident())
        return original_refresh()

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

    asyncio.run(exercise())


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

    def move(selected, _accounts):
        if selected.header_message_id == second.header_message_id:
            raise RuntimeError("injected failure")
        moved.append(selected.header_message_id)

    monkeypatch.setattr(
        "examples.mail_assistant.web_app.move_message_to_trash",
        move,
    )

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            page = await client.get("/")
            assert "Review selected for Trash…" in page.text
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
                "examples.mail_assistant.web_app.time.time", lambda: 1_000.0
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
                "examples.mail_assistant.web_app.time.time", lambda: 2_000.0
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


def test_batch_trash_proposal_rejects_any_unsafe_or_unmapped_message(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "imap.toml"
    config_path.write_text(
        "[[account]]\nhost='imap.example.test'\nusername='user@example.test'\n"
        "password_env='TEST_IMAP_PASSWORD'\ntrash_folder='Trash'\n",
        encoding="utf-8",
    )
    good = _message(
        "good@example.test",
        folder_uri="imap://user%40example.test@imap.example.test/INBOX",
    )
    hostile = _message(
        "hostile@example.test\r\nEXPUNGE",
        folder_uri="imap://user%40example.test@imap.example.test/INBOX",
    )
    unmapped = _message(
        "unmapped@example.test",
        folder_uri="imap://user%40example.test@other.example.test/INBOX",
    )
    app = _web_app(tmp_path, good, imap_accounts_path=config_path)

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            for rejected in (hostile, unmapped):
                app.state.mail._reader = lambda _path, item=rejected: [good, item]
                app.state.mail.refresh()
                response = await client.post(
                    "/trash/propose",
                    data={
                        "message_ids": [good.header_message_id, rejected.header_message_id],
                        "csrf_token": app.state.csrf_token,
                    },
                )
                assert response.status_code == 400

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

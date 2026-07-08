"""Secured localhost FastAPI surface for the mail assistant."""
# ruff: noqa: E402 -- repository bootstrap must run before sibling-package imports
from __future__ import annotations

from dataclasses import dataclass
from contextlib import asynccontextmanager
import configparser
import os
import asyncio
import threading
import time
from pathlib import Path
import secrets
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ._bootstrap import install_repo_source_paths

install_repo_source_paths()

from llm_engines import get_engine

from mail_lib.personal_rules import RuleAction, RuleLoadResult, empty_rule_result, load_personal_rules
from mail_lib.thunderbird import MailMessage
from mail_lib.triage import Priority

from .rules import RuleTransactionService
from .services import MailAssistantService, PRIORITY_ORDER
from .store import AssistantStore, DEFAULT_STORE_PATH
from .summarizer import SectionSummarizer
from .imap_trash import (
    account_for_message,
    load_imap_accounts,
    move_messages_to_trash,
    validate_move_candidate,
    verify_messages_available_for_move,
)


APP_DIR = Path(__file__).resolve().parent
DEFAULT_WINDOW_VALUE = 1
DEFAULT_WINDOW_UNIT = "weeks"


async def _run_blocking(function, *args, timeout: float | None = None):
    """Run blocking local I/O without depending on AnyIO's worker-thread bridge.

    A timeout stops waiting for the result; it cannot cancel the underlying daemon
    thread. The operation may therefore finish later and retain its side effects
    (for example, a completed summary may still populate the cache).
    """
    complete = threading.Event()
    outcome: dict[str, Any] = {}

    def invoke() -> None:
        try:
            outcome["value"] = function(*args)
        except BaseException as exc:  # re-raised in the request task
            outcome["error"] = exc
        finally:
            complete.set()

    threading.Thread(target=invoke, daemon=True, name="mail-assistant-worker").start()
    deadline = None if timeout is None else time.monotonic() + timeout
    while not complete.is_set():
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("Blocking operation timed out")
        await asyncio.sleep(0.01)
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


@dataclass(frozen=True)
class AppConfig:
    profile: Path
    rules_path: Path
    database_path: Path = DEFAULT_STORE_PATH
    backend: str = "ollama"
    model: str = "qwen3:8b"
    input_budget: int = 12_000
    output_tokens: int = 800
    model_timeout: float = 120.0
    imap_accounts_path: Path | None = None


def _discover_thunderbird_profile(thunderbird_root: Path | None = None) -> Path:
    root = thunderbird_root or Path.home() / ".thunderbird"
    parser = configparser.ConfigParser()
    profiles_path = root / "profiles.ini"
    if not parser.read(profiles_path, encoding="utf-8"):
        raise RuntimeError(
            "Thunderbird profile was not configured and profiles.ini was not found; "
            "set MAIL_ASSISTANT_PROFILE"
        )
    candidates: list[Path] = []
    for section in parser.sections():
        if not section.startswith("Profile") or not parser.getboolean(
            section, "Default", fallback=False
        ):
            continue
        configured = Path(parser.get(section, "Path", fallback=""))
        if not configured.parts:
            continue
        candidates.append(
            root / configured
            if parser.getboolean(section, "IsRelative", fallback=True)
            else configured
        )
    existing = [candidate for candidate in candidates if candidate.is_dir()]
    if len(existing) != 1:
        raise RuntimeError(
            "Could not identify one default Thunderbird profile; set MAIL_ASSISTANT_PROFILE"
        )
    return existing[0]


def _default_config() -> AppConfig:
    config_home = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    configured_profile = os.getenv("MAIL_ASSISTANT_PROFILE")
    return AppConfig(
        profile=(
            Path(configured_profile)
            if configured_profile
            else _discover_thunderbird_profile()
        ),
        rules_path=Path(
            os.getenv("MAIL_ASSISTANT_RULES", config_home / "mail_lib" / "personal_rules.toml")
        ),
        database_path=Path(os.getenv("MAIL_ASSISTANT_DB", DEFAULT_STORE_PATH)),
        backend=os.getenv("MAIL_ASSISTANT_BACKEND", "ollama"),
        model=os.getenv("MAIL_ASSISTANT_MODEL", "qwen3:8b"),
        imap_accounts_path=Path(
            os.getenv(
                "MAIL_ASSISTANT_IMAP_ACCOUNTS",
                config_home / "mail_assistant" / "imap_accounts.toml",
            )
        ),
    )


def create_app(config: AppConfig, *, engine: Any | None = None) -> FastAPI:
    templates = Jinja2Templates(directory=APP_DIR / "templates")
    csrf_token = secrets.token_urlsafe(32)
    store = AssistantStore(config.database_path)
    imap_accounts = load_imap_accounts(config.imap_accounts_path) if config.imap_accounts_path else ()
    prefs_cache = {}

    def include_message(message: MailMessage) -> bool:
        if not imap_accounts:
            return True
        try:
            account, folder = account_for_message(
                message,
                imap_accounts,
                prefs_cache=prefs_cache,
            )
        except ValueError:
            return True
        observed_folders = (folder, *message.signal_folders)
        return all(
            observed.casefold().strip("/")
            != account.trash_folder.casefold().strip("/")
            for observed in observed_folders
        )

    mail = MailAssistantService(
        config.profile,
        store,
        include_message=include_message,
    )
    rule_transactions = RuleTransactionService(config.rules_path)
    pending_trash: dict[str, tuple[tuple[str, ...], float]] = {}
    summary_service: SectionSummarizer | None = None

    async def refresh_in_background(target_app: FastAPI) -> None:
        target_app.state.refresh_error = None
        try:
            await _run_blocking(mail.refresh)
        except Exception as exc:
            target_app.state.refresh_error = str(exc)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        mail.load_cached()
        _app.state.refresh_task = asyncio.create_task(refresh_in_background(_app))
        try:
            yield
        finally:
            task = _app.state.refresh_task
            if task and not task.done():
                task.cancel()

    app = FastAPI(title="Local Mail Assistant", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )
    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
    app.state.config = config
    app.state.mail = mail
    app.state.store = store
    app.state.csrf_token = csrf_token
    app.state.refresh_task = None
    app.state.refresh_error = None

    def start_background_refresh() -> bool:
        task = app.state.refresh_task
        if task is not None and not task.done():
            return False
        app.state.refresh_task = asyncio.create_task(refresh_in_background(app))
        return True

    @app.middleware("http")
    async def response_security(request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    def require_csrf(request: Request, supplied: str) -> None:
        if not secrets.compare_digest(supplied, csrf_token):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")
        # Firefox suppresses both Origin and Referer under our no-referrer
        # policy on same-origin POSTs, so absent headers must pass; the token
        # is the primary gate. A *present* mismatched Origin is still rejected.
        origin = request.headers.get("origin")
        if origin and origin != "null":
            expected = str(request.base_url).rstrip("/")
            if origin.rstrip("/") != expected:
                raise HTTPException(status_code=403, detail="Cross-origin request rejected")

    def current_rules() -> RuleLoadResult:
        if not config.rules_path.exists():
            return empty_rule_result()
        result = load_personal_rules(config.rules_path)
        if not result.ok:
            raise HTTPException(status_code=500, detail="Personal rules are invalid")
        return result

    def window_days(value: int, unit: str) -> int:
        if unit not in {"days", "weeks"}:
            raise HTTPException(status_code=400, detail="Window unit must be days or weeks")
        if not 1 <= value <= 3650:
            raise HTTPException(status_code=400, detail="Window value must be between 1 and 3650")
        return value * (7 if unit == "weeks" else 1)

    def display_limit(value: int) -> int:
        if not 1 <= value <= 500:
            raise HTTPException(status_code=400, detail="Display limit must be between 1 and 500")
        return value

    def context(
        request: Request,
        *,
        view: str,
        window_value: int,
        window_unit: str,
        notice: str | None = None,
        sender_filter: str | None = None,
        domain_filter: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        rules = current_rules()
        task = app.state.refresh_task
        if notice is None and task is not None and not task.done():
            notice = "Snapshot refresh is running in the background."
        if notice is None and app.state.refresh_error:
            notice = f"Snapshot refresh failed: {app.state.refresh_error}"
        try:
            groups = mail.visible(
                rules.rules,
                view=view,
                max_age_days=window_days(window_value, window_unit),
                sender_filter=sender_filter,
                domain_filter=domain_filter,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        trash_eligible_ids: set[str] = set()
        trash_status_by_id: dict[str, str] = {}
        if imap_accounts:
            for messages in groups.values():
                for item in messages:
                    message_id = item.message.header_message_id
                    try:
                        account, folder = validate_move_candidate(
                            item.message,
                            imap_accounts,
                            prefs_cache=prefs_cache,
                        )
                    except ValueError as exc:
                        trash_status_by_id[message_id] = str(exc)
                        continue
                    trash_eligible_ids.add(message_id)
                    trash_status_by_id[message_id] = (
                        f"Trash target: {account.username} {folder} → "
                        f"{account.trash_folder}"
                    )
        return {
            "request": request,
            "view": view,
            "groups": groups,
            "priorities": PRIORITY_ORDER,
            "csrf_token": csrf_token,
            "notice": notice,
            "window_value": window_value,
            "window_unit": window_unit,
            "refresh_running": bool(task is not None and not task.done()),
            "trash_enabled": bool(imap_accounts),
            "trash_eligible_ids": trash_eligible_ids,
            "trash_status_by_id": trash_status_by_id,
            "sender_filter": sender_filter or "",
            "domain_filter": domain_filter or "",
            "display_limit": display_limit(limit),
        }

    @app.get("/", response_class=HTMLResponse)
    async def index(
        request: Request,
        view: str = "unread",
        window_value: int = DEFAULT_WINDOW_VALUE,
        window_unit: str = DEFAULT_WINDOW_UNIT,
        sender: str | None = None,
        domain: str | None = None,
        limit: int = 50,
    ):
        return templates.TemplateResponse(
            request,
            "index.html",
            context(
                request,
                view=view,
                window_value=window_value,
                window_unit=window_unit,
                sender_filter=sender,
                domain_filter=domain,
                limit=limit,
            ),
        )

    @app.get("/stats", response_class=HTMLResponse)
    async def stats(
        request: Request,
        window_value: int = DEFAULT_WINDOW_VALUE,
        window_unit: str = DEFAULT_WINDOW_UNIT,
    ):
        days = window_days(window_value, window_unit)
        sender_stats, domain_stats = mail.volume_stats(max_age_days=days)
        return templates.TemplateResponse(
            request,
            "stats.html",
            {
                "request": request,
                "sender_stats": sender_stats,
                "domain_stats": domain_stats,
                "window_value": window_value,
                "window_unit": window_unit,
                "csrf_token": csrf_token,
            },
        )

    @app.post("/refresh", response_class=HTMLResponse)
    async def refresh(
        request: Request,
        csrf_token: str = Form(...),
        view: str = Form("unread"),
        window_value: int = Form(DEFAULT_WINDOW_VALUE),
        window_unit: str = Form(DEFAULT_WINDOW_UNIT),
        sender_filter: str | None = Form(None),
        domain_filter: str | None = Form(None),
    ):
        require_csrf(request, csrf_token)
        start_background_refresh()
        query = urlencode(
            {"view": view, "window_value": window_value, "window_unit": window_unit}
        )
        return RedirectResponse(url=f"/?{query}", status_code=303)

    @app.get("/refresh-status")
    async def refresh_status() -> Response:
        task = app.state.refresh_task
        if task is not None and not task.done():
            return HTMLResponse(
                '<div id="refresh-status" hx-get="/refresh-status" '
                'hx-trigger="load delay:2s" hx-swap="outerHTML">'
                "Loading mail snapshot in the background…</div>"
            )
        return Response(status_code=204, headers={"HX-Refresh": "true"})

    @app.get("/message", response_class=HTMLResponse)
    async def message_detail(request: Request, message_id: str):
        message = next(
            (item for item in mail.state.messages if item.header_message_id == message_id),
            None,
        )
        if message is None:
            raise HTTPException(status_code=404, detail="Unknown message ID")
        return templates.TemplateResponse(
            request,
            "message_detail.html",
            {"request": request, "message": message},
        )

    @app.post("/read", response_class=HTMLResponse)
    async def mark_read(
        request: Request,
        message_id: str = Form(...),
        csrf_token: str = Form(...),
        view: str = Form("unread"),
        window_value: int = Form(DEFAULT_WINDOW_VALUE),
        window_unit: str = Form(DEFAULT_WINDOW_UNIT),
        sender_filter: str | None = Form(None),
        domain_filter: str | None = Form(None),
    ):
        require_csrf(request, csrf_token)
        try:
            mail.mark_read(message_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown message ID") from exc
        return templates.TemplateResponse(
            request,
            "mail_list.html",
            context(request, view=view, window_value=window_value, window_unit=window_unit),
        )

    @app.post("/trash/propose", response_class=HTMLResponse)
    async def propose_trash(
        request: Request,
        message_ids: list[str] = Form(...),
        csrf_token: str = Form(...),
        view: str = Form("unread"),
        window_value: int = Form(DEFAULT_WINDOW_VALUE),
        window_unit: str = Form(DEFAULT_WINDOW_UNIT),
    ):
        require_csrf(request, csrf_token)
        selected_ids = tuple(dict.fromkeys(message_ids))
        if not selected_ids:
            raise HTTPException(status_code=400, detail="Select at least one message")
        by_id = {item.header_message_id: item for item in mail.state.messages}
        if any(message_id not in by_id for message_id in selected_ids):
            raise HTTPException(status_code=404, detail="Unknown message ID in selection")
        rows = []
        selected_messages = tuple(by_id[message_id] for message_id in selected_ids)
        try:
            for message in selected_messages:
                account, folder = validate_move_candidate(
                    message,
                    imap_accounts,
                    prefs_cache=prefs_cache,
                )
                rows.append(
                    {
                        "message": message,
                        "host": account.host,
                        "folder": folder,
                        "trash_folder": account.trash_folder,
                    }
                )

            def preflight_selected_messages() -> None:
                verify_messages_available_for_move(
                    selected_messages,
                    imap_accounts,
                    prefs_cache=prefs_cache,
                )

            await _run_blocking(preflight_selected_messages, timeout=120)
        except Exception as exc:
            return templates.TemplateResponse(
                request,
                "trash_error.html",
                {
                    "request": request,
                    "message": message,
                    "error": str(exc),
                },
                status_code=400,
            )
        token = secrets.token_urlsafe(32)
        now = time.time()
        for expired_token in [
            key for key, value in pending_trash.items() if value[1] < now
        ]:
            pending_trash.pop(expired_token, None)
        pending_trash[token] = (selected_ids, now + 600)
        return templates.TemplateResponse(
            request,
            "trash_proposal.html",
            {
                "request": request,
                "rows": rows,
                "token": token,
                "csrf_token": csrf_token,
                "view": view,
                "window_value": window_value,
                "window_unit": window_unit,
            },
        )

    @app.post("/trash/commit", response_class=HTMLResponse)
    async def commit_trash(
        request: Request,
        trash_token: str = Form(...),
        csrf_token: str = Form(...),
        view: str = Form("unread"),
        window_value: int = Form(DEFAULT_WINDOW_VALUE),
        window_unit: str = Form(DEFAULT_WINDOW_UNIT),
    ):
        require_csrf(request, csrf_token)
        pending = pending_trash.pop(trash_token, None)
        if pending is None or pending[1] < time.time():
            raise HTTPException(status_code=400, detail="Unknown or expired trash token")
        selected_ids = pending[0]
        by_id = {item.header_message_id: item for item in mail.state.messages}
        outcomes = []
        messages_to_move = []
        for message_id in selected_ids:
            message = by_id.get(message_id)
            if message is None:
                outcomes.append({"message_id": message_id, "subject": "", "status": "skipped", "detail": "Message left the snapshot before confirmation."})
                continue
            messages_to_move.append(message)
        if messages_to_move:

            def move_selected_messages() -> dict[str, str | None]:
                return move_messages_to_trash(
                    tuple(messages_to_move),
                    imap_accounts,
                    prefs_cache=prefs_cache,
                )

            move_results = await _run_blocking(move_selected_messages, timeout=120)
        else:
            move_results = {}
        moved_ids = []
        for message in messages_to_move:
            detail = move_results.get(message.header_message_id)
            if detail is None:
                moved_ids.append(message.header_message_id)
                outcomes.append({"message_id": message.header_message_id, "subject": message.subject, "status": "moved", "detail": "Moved to Trash."})
            else:
                outcomes.append({"message_id": message.header_message_id, "subject": message.subject, "status": "failed", "detail": detail})
        if moved_ids:
            mail.remove_messages(moved_ids)
        return templates.TemplateResponse(
            request,
            "trash_outcomes.html",
            {
                "request": request,
                "outcomes": outcomes,
                "moved_count": len(moved_ids),
                "failed_count": sum(item["status"] == "failed" for item in outcomes),
                "skipped_count": sum(item["status"] == "skipped" for item in outcomes),
                "return_url": f"/?{urlencode({'view': view, 'window_value': window_value, 'window_unit': window_unit})}",
            },
        )

    @app.post("/summarize/{section}", response_class=HTMLResponse)
    async def summarize(
        section: Priority,
        request: Request,
        csrf_token: str = Form(...),
        view: str = Form("unread"),
        window_value: int = Form(DEFAULT_WINDOW_VALUE),
        window_unit: str = Form(DEFAULT_WINDOW_UNIT),
        sender_filter: str | None = Form(None),
        domain_filter: str | None = Form(None),
        summary_limit: int = Form(50),
    ):
        nonlocal summary_service
        require_csrf(request, csrf_token)
        messages = mail.visible(
            current_rules().rules,
            view=view,
            max_age_days=window_days(window_value, window_unit),
            sender_filter=sender_filter,
            domain_filter=domain_filter,
        )[section][:display_limit(summary_limit)]
        if not messages:
            raise HTTPException(status_code=404, detail="Section is empty")
        if summary_service is None:
            actual_engine = engine or get_engine(config.backend, config.model)
            summary_service = SectionSummarizer(
                actual_engine,
                store,
                model=config.model,
                input_budget=config.input_budget,
                output_tokens=config.output_tokens,
            )
        try:
            summary = await _run_blocking(
                summary_service.summarize,
                messages,
                timeout=config.model_timeout,
            )
        except TimeoutError:
            return templates.TemplateResponse(
                request,
                "summary_error.html",
                {"request": request, "detail": "Summary timed out. Try a smaller display limit."},
            )
        except Exception as exc:
            return templates.TemplateResponse(
                request,
                "summary_error.html",
                {"request": request, "detail": f"Summary failed: {exc}"},
            )
        return templates.TemplateResponse(
            request,
            "summary.html",
            {
                "request": request,
                "summary": summary,
                "section": section.value,
                "message_count": len(messages),
            },
        )

    @app.post("/rules/propose", response_class=HTMLResponse)
    async def propose_rule(
        request: Request,
        message_id: str | None = Form(None),
        match_value: str | None = Form(None),
        field: str = Form(...),
        priority: Priority = Form(...),
        action: RuleAction = Form(...),
        csrf_token: str = Form(...),
        view: str = Form("unread"),
        window_value: int = Form(DEFAULT_WINDOW_VALUE),
        window_unit: str = Form(DEFAULT_WINDOW_UNIT),
    ):
        require_csrf(request, csrf_token)
        messages = {item.header_message_id: item for item in mail.state.messages}
        message = messages.get(message_id) if message_id else None
        if message_id and message is None:
            raise HTTPException(status_code=404, detail="Unknown message ID")
        try:
            proposal = rule_transactions.propose(
                message,
                field=field,
                priority=priority,
                action=action,
                match_value=match_value,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return templates.TemplateResponse(
            request,
            "rule_proposal.html",
            {
                "request": request,
                "proposal": proposal,
                "csrf_token": csrf_token,
                "view": view,
                "window_value": window_value,
                "window_unit": window_unit,
            },
        )

    @app.post("/rules/commit", response_class=HTMLResponse)
    async def commit_rule(
        request: Request,
        proposal_token: str = Form(...),
        csrf_token: str = Form(...),
        view: str = Form("unread"),
        window_value: int = Form(DEFAULT_WINDOW_VALUE),
        window_unit: str = Form(DEFAULT_WINDOW_UNIT),
    ):
        require_csrf(request, csrf_token)
        try:
            rule_transactions.commit(proposal_token)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return templates.TemplateResponse(
            request,
            "index.html",
            context(
                request,
                view=view,
                window_value=window_value,
                window_unit=window_unit,
                notice="Rule committed.",
            ),
        )

    return app


def main() -> None:
    import uvicorn

    host = os.getenv("MAIL_ASSISTANT_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("MAIL_ASSISTANT_HOST must be loopback")
    port = int(os.getenv("MAIL_ASSISTANT_PORT", "8091"))
    uvicorn.run(lambda: create_app(_default_config()), host=host, port=port, factory=True, reload=False)


if __name__ == "__main__":
    main()

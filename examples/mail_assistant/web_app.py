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

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ._bootstrap import install_repo_source_paths

install_repo_source_paths()

from llm_engines import get_engine

from mail_lib.personal_rules import RuleAction, RuleLoadResult, empty_rule_result, load_personal_rules
from mail_lib.triage import Priority

from .rules import RuleTransactionService
from .services import MailAssistantService, PRIORITY_ORDER
from .store import AssistantStore, DEFAULT_STORE_PATH
from .summarizer import SectionSummarizer


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
    )


def create_app(config: AppConfig, *, engine: Any | None = None) -> FastAPI:
    templates = Jinja2Templates(directory=APP_DIR / "templates")
    csrf_token = secrets.token_urlsafe(32)
    store = AssistantStore(config.database_path)
    mail = MailAssistantService(config.profile, store)
    rule_transactions = RuleTransactionService(config.rules_path)
    summary_service: SectionSummarizer | None = None

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await _run_blocking(mail.refresh)
        yield

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

    def require_csrf(_request: Request, supplied: str) -> None:
        if not secrets.compare_digest(supplied, csrf_token):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")

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

    def context(
        request: Request,
        *,
        view: str,
        window_value: int,
        window_unit: str,
        notice: str | None = None,
    ) -> dict[str, Any]:
        rules = current_rules()
        try:
            groups = mail.visible(
                rules.rules,
                view=view,
                max_age_days=window_days(window_value, window_unit),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "request": request,
            "view": view,
            "groups": groups,
            "priorities": PRIORITY_ORDER,
            "csrf_token": csrf_token,
            "notice": notice,
            "window_value": window_value,
            "window_unit": window_unit,
        }

    @app.get("/", response_class=HTMLResponse)
    async def index(
        request: Request,
        view: str = "unread",
        window_value: int = DEFAULT_WINDOW_VALUE,
        window_unit: str = DEFAULT_WINDOW_UNIT,
    ):
        return templates.TemplateResponse(
            request,
            "index.html",
            context(request, view=view, window_value=window_value, window_unit=window_unit),
        )

    @app.post("/refresh", response_class=HTMLResponse)
    async def refresh(
        request: Request,
        csrf_token: str = Form(...),
        view: str = Form("unread"),
        window_value: int = Form(DEFAULT_WINDOW_VALUE),
        window_unit: str = Form(DEFAULT_WINDOW_UNIT),
    ):
        require_csrf(request, csrf_token)
        try:
            await _run_blocking(mail.refresh)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Refresh failed: {exc}") from exc
        return templates.TemplateResponse(
            request,
            "index.html",
            context(
                request,
                view=view,
                window_value=window_value,
                window_unit=window_unit,
                notice="Snapshot refreshed.",
            ),
        )

    @app.post("/read", response_class=HTMLResponse)
    async def mark_read(
        request: Request,
        message_id: str = Form(...),
        csrf_token: str = Form(...),
        view: str = Form("unread"),
        window_value: int = Form(DEFAULT_WINDOW_VALUE),
        window_unit: str = Form(DEFAULT_WINDOW_UNIT),
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

    @app.post("/summarize/{section}", response_class=HTMLResponse)
    async def summarize(
        section: Priority,
        request: Request,
        csrf_token: str = Form(...),
        view: str = Form("unread"),
        window_value: int = Form(DEFAULT_WINDOW_VALUE),
        window_unit: str = Form(DEFAULT_WINDOW_UNIT),
    ):
        nonlocal summary_service
        require_csrf(request, csrf_token)
        messages = mail.visible(
            current_rules().rules,
            view=view,
            max_age_days=window_days(window_value, window_unit),
        )[section]
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
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail="Summary timed out") from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Summary failed: {exc}") from exc
        return templates.TemplateResponse(
            request,
            "summary.html",
            {"request": request, "summary": summary, "section": section.value},
        )

    @app.post("/rules/propose", response_class=HTMLResponse)
    async def propose_rule(
        request: Request,
        message_id: str = Form(...),
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
        message = messages.get(message_id)
        if message is None:
            raise HTTPException(status_code=404, detail="Unknown message ID")
        try:
            proposal = rule_transactions.propose(
                message, field=field, priority=priority, action=action
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

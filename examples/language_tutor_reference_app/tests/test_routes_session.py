import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from language_tutor.routes.session import (
    ActiveSessionRegistry,
    EndSessionRequest,
    active_sessions,
    end_session,
    get_session_status,
)


def test_missing_session_statuses_remain_not_found():
    active_sessions.clear()
    with pytest.raises(HTTPException) as end_error:
        asyncio.run(end_session(EndSessionRequest(session_id="missing")))
    with pytest.raises(HTTPException) as status_error:
        asyncio.run(get_session_status("missing"))
    assert end_error.value.status_code == 404
    assert status_error.value.status_code == 404


def test_session_lookup_refreshes_last_activity(monkeypatch):
    registry = ActiveSessionRegistry()
    session = SimpleNamespace(last_activity=10.0)
    registry["s1"] = session
    monkeypatch.setattr("language_tutor.routes.session.time.time", lambda: 25.0)

    assert registry.get("s1") is session
    assert session.last_activity == 25.0

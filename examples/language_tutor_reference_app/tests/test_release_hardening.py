import asyncio
import importlib
import json
import sys

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "language_tutor.drills.base",
    ],
)
def test_release_compat_modules_import(module_name):
    if module_name == "language_tutor.drills.base":
        with pytest.warns(DeprecationWarning):
            module = importlib.import_module(module_name)
    else:
        module = importlib.import_module(module_name)

    assert module is not None


def _reload_app_module(monkeypatch, *, debug: bool):
    monkeypatch.setenv("LANGUAGE_TUTOR_DEBUG_EXCEPTIONS", "1" if debug else "0")
    sys.modules.pop("language_tutor.app", None)
    return importlib.import_module("language_tutor.app")


def test_exception_handler_hides_traceback_by_default(monkeypatch):
    app_module = _reload_app_module(monkeypatch, debug=False)
    response = asyncio.run(app_module.debug_exception_handler(None, RuntimeError("boom")))
    payload = json.loads(response.body.decode("utf-8"))
    assert payload == {"error": "Internal server error"}


def test_exception_handler_shows_traceback_in_debug(monkeypatch):
    app_module = _reload_app_module(monkeypatch, debug=True)
    response = asyncio.run(app_module.debug_exception_handler(None, RuntimeError("boom")))
    payload = json.loads(response.body.decode("utf-8"))
    assert payload["error"] == "boom"
    assert "traceback" in payload


def test_server_entry_point_binds_only_to_loopback(monkeypatch):
    app_module = _reload_app_module(monkeypatch, debug=False)
    calls = []
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append((args, kwargs)))

    app_module.main()

    assert calls[0][1]["host"] == "127.0.0.1"

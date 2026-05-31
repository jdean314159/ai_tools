from __future__ import annotations


def test_ui_app_imports_without_streamlit_server() -> None:
    from diagnostics_agent.ui import app

    assert callable(app.main)

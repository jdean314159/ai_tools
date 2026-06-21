from pathlib import Path
import sys

import pytest
from streamlit.web import cli as stcli

from llm_inspector_ui import __main__ as launcher


def test_main_launches_packaged_app_with_streamlit(monkeypatch):
    captured_argv: list[str] = []

    def fake_streamlit_main() -> int:
        captured_argv.extend(sys.argv)
        return 0

    monkeypatch.setattr(stcli, "main", fake_streamlit_main)

    with pytest.raises(SystemExit) as exc_info:
        launcher.main()

    assert exc_info.value.code == 0
    assert captured_argv == [
        "streamlit",
        "run",
        str(Path(launcher.__file__).parent / "app.py"),
        "--server.port",
        "8501",
    ]

"""Entry point for `python -m llm_inspector_ui`."""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    try:
        from streamlit.web import cli as stcli
    except ImportError:
        sys.exit(
            "streamlit is not installed. "
            "Run: pip install llm-inspector-ui"
        )
    app = str(Path(__file__).parent / "app.py")
    sys.argv = ["streamlit", "run", app, "--server.port", "8501"]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()

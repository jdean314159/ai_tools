import importlib.util
import sys
import pytest


def test_importing_llm_inspector_does_not_import_engram():
    sys.modules.pop("engram", None)
    import llm_inspector  # noqa: F401

    assert "engram" not in sys.modules


def test_engram_adapter_errors_cleanly():
    from llm_inspector.adapters.engram_adapter import make_engram

    engram_available = importlib.util.find_spec("engram") is not None

    if not engram_available:
        with pytest.raises(RuntimeError) as e:
            make_engram()
        msg = str(e.value)
        assert "requires Engram installed" in msg
        assert "llm_inspector[engram]" in msg
    else:
        # Engram is installed; adapter is implemented. base_dir is required.
        with pytest.raises(TypeError):
            make_engram()

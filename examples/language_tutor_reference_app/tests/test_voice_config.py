from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace


def test_stt_environment_overrides_device_and_compute_type(monkeypatch) -> None:
    created: dict[str, object] = {}

    class FakeWhisperModel:
        def __init__(self, model_name: str, **kwargs: object) -> None:
            created.update(model_name=model_name, **kwargs)

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=FakeWhisperModel),
    )
    monkeypatch.setenv("WHISPER_DEVICE", "cpu")
    monkeypatch.setenv("WHISPER_COMPUTE_TYPE", "int8")
    sys.modules.pop("language_tutor.voice.stt", None)

    module = importlib.import_module("language_tutor.voice.stt")
    service = module.STTService()
    try:
        assert service.device == "cpu"
        assert service.compute_type == "int8"
        assert created["device"] == "cpu"
        assert created["compute_type"] == "int8"
    finally:
        service.close()

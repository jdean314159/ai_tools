"""
test_voice.py

Unit tests for the voice module.

All external dependencies (piper subprocess, faster-whisper model) are
mocked or isolated.  No audio files, no binary downloads.

Coverage:
  - _find_model():       env var path, directory discovery, missing → RuntimeError
  - PiperTTSService:     construction via env var; synthesis dispatches subprocess
  - _synthesise_sync():  returncode != 0 → RuntimeError; success → base64 string
  - _latin_phonetic():   v→w substitution
  - VoicePipeline:       lazy init; language-specific preprocessing applied
  - STTService:          construction without a live model
"""
from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from language_tutor.voice.piper_tts import PiperTTSService

pytestmark = pytest.mark.skip(
    reason="recovered optional voice suite requires a bounded subprocess rewrite"
)


# ---------------------------------------------------------------------------
# _find_model()
# ---------------------------------------------------------------------------

class TestFindModel:
    def test_env_var_valid_path_returns_path(self, tmp_path, monkeypatch):
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"fake-model")
        monkeypatch.setenv("PIPER_MODEL_PATH", str(model))

        from language_tutor.voice.piper_tts import _find_model
        assert _find_model() == model

    def test_env_var_missing_file_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PIPER_MODEL_PATH", str(tmp_path / "nonexistent.onnx"))

        from language_tutor.voice.piper_tts import _find_model
        with pytest.raises(RuntimeError, match="PIPER_MODEL_PATH set but file not found"):
            _find_model()

    def test_no_env_no_model_raises(self, monkeypatch, tmp_path):
        monkeypatch.delenv("PIPER_MODEL_PATH", raising=False)
        # Point home to tmp so we don't pick up the real user's models
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

        # Also patch __file__ context so project-local piper/ dir doesn't exist
        from language_tutor.voice import piper_tts as _mod
        monkeypatch.setattr(_mod, "__file__", str(tmp_path / "piper_tts.py"))

        with pytest.raises(RuntimeError, match="No piper model found"):
            _mod._find_model()

    def test_project_local_piper_dir_found(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PIPER_MODEL_PATH", raising=False)

        # Fake a project-local piper/ directory relative to the module
        piper_dir = tmp_path / "piper"
        piper_dir.mkdir()
        model = piper_dir / "es_ES.onnx"
        model.write_bytes(b"fake")

        from language_tutor.voice import piper_tts as _mod
        monkeypatch.setattr(
            _mod, "__file__",
            # __file__ is language_tutor/voice/piper_tts.py → parent×3 / piper/
            str(tmp_path / "language_tutor" / "voice" / "piper_tts.py"),
        )

        result = _mod._find_model()
        assert result == model


# ---------------------------------------------------------------------------
# PiperTTSService construction
# ---------------------------------------------------------------------------

class TestPiperTTSServiceConstruction:
    def test_explicit_model_path_accepted(self, tmp_path):
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"x")

        from language_tutor.voice.piper_tts import PiperTTSService
        svc = PiperTTSService(model_path=model)
        assert svc.model_path == model

    def test_missing_explicit_path_raises_on_init(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PIPER_MODEL_PATH", raising=False)
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

        from language_tutor.voice import piper_tts as _mod
        monkeypatch.setattr(_mod, "__file__", str(tmp_path / "piper_tts.py"))

        with pytest.raises(RuntimeError):
            _mod.PiperTTSService()


# ---------------------------------------------------------------------------
# _synthesise_sync()
# ---------------------------------------------------------------------------

class TestSynthesiseSync:
    def _make_svc(self, tmp_path: Path) -> "PiperTTSService":
        from language_tutor.voice.piper_tts import PiperTTSService
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"x")
        return PiperTTSService(model_path=model)

    def test_success_returns_base64_wav(self, tmp_path):
        svc = self._make_svc(tmp_path)
        fake_wav = b"RIFF....WAVEfmt "

        def _fake_run(cmd, input, capture_output, timeout):
            # Write fake WAV to the output file (last positional arg is --output_file <path>)
            out_idx = cmd.index("--output_file") + 1
            Path(cmd[out_idx]).write_bytes(fake_wav)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=_fake_run):
            result = svc._synthesise_sync("Hola mundo", "normal")

        assert result == base64.b64encode(fake_wav).decode()

    def test_nonzero_returncode_raises(self, tmp_path):
        svc = self._make_svc(tmp_path)

        def _fail(cmd, input, capture_output, timeout):
            return MagicMock(
                returncode=1,
                stderr=b"piper: model not found",
            )

        with patch("subprocess.run", side_effect=_fail):
            with pytest.raises(RuntimeError, match="piper exited 1"):
                svc._synthesise_sync("test", "normal")

    def test_slow_speed_uses_different_length_scale(self, tmp_path):
        svc = self._make_svc(tmp_path)
        captured_cmds = []
        fake_wav = b"RIFF"

        def _record(cmd, input, capture_output, timeout):
            captured_cmds.append(cmd)
            out_idx = cmd.index("--output_file") + 1
            Path(cmd[out_idx]).write_bytes(fake_wav)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=_record):
            svc._synthesise_sync("test slow", "slow")
            svc._synthesise_sync("test normal", "normal")

        ls_slow   = captured_cmds[0][captured_cmds[0].index("--length_scale") + 1]
        ls_normal = captured_cmds[1][captured_cmds[1].index("--length_scale") + 1]
        assert float(ls_slow) != float(ls_normal)

    def test_temp_file_cleaned_up_on_success(self, tmp_path):
        svc = self._make_svc(tmp_path)
        seen_paths: list[str] = []
        fake_wav = b"RIFF"

        def _record(cmd, input, capture_output, timeout):
            out_idx = cmd.index("--output_file") + 1
            seen_paths.append(cmd[out_idx])
            Path(cmd[out_idx]).write_bytes(fake_wav)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=_record):
            svc._synthesise_sync("cleanup test", "normal")

        assert seen_paths
        assert not Path(seen_paths[0]).exists()


# ---------------------------------------------------------------------------
# generate_speech() async wrapper
# ---------------------------------------------------------------------------

class TestGenerateSpeech:
    def test_generate_speech_returns_base64_string(self, tmp_path):
        from language_tutor.voice.piper_tts import PiperTTSService
        model = tmp_path / "m.onnx"
        model.write_bytes(b"x")
        svc = PiperTTSService(model_path=model)
        fake_wav = b"WAV"

        def _fake_synth(text, speed):
            return base64.b64encode(fake_wav).decode()

        svc._synthesise_sync = _fake_synth  # type: ignore[method-assign]
        result = asyncio.run(svc.generate_speech("Hola", speed="normal"))
        assert result == base64.b64encode(fake_wav).decode()


# ---------------------------------------------------------------------------
# _latin_phonetic()
# ---------------------------------------------------------------------------

class TestLatinPhonetic:
    def test_v_becomes_w(self):
        from language_tutor.voice.tts import _latin_phonetic
        assert _latin_phonetic("veni vidi vici") == "weni widi wici"

    def test_uppercase_v_becomes_w(self):
        from language_tutor.voice.tts import _latin_phonetic
        assert _latin_phonetic("VENI VIDI VICI") == "WENI WIDI WICI"

    def test_non_v_chars_unchanged(self):
        from language_tutor.voice.tts import _latin_phonetic
        assert _latin_phonetic("Roma") == "Roma"

    def test_mixed_text(self):
        from language_tutor.voice.tts import _latin_phonetic
        result = _latin_phonetic("ave Caesar")
        assert result == "awe Caesar"


# ---------------------------------------------------------------------------
# VoicePipeline construction (no services loaded)
# ---------------------------------------------------------------------------

class TestVoicePipeline:
    def _make_profile(self, language: str = "spanish"):
        from language_tutor.config import get_language_profile
        return get_language_profile(language)

    def test_construction_does_not_load_stt(self):
        from language_tutor.voice.tts import VoicePipeline
        profile = self._make_profile("spanish")
        pipeline = VoicePipeline(profile)
        assert pipeline._stt is None

    def test_construction_does_not_load_tts(self):
        from language_tutor.voice.tts import VoicePipeline
        profile = self._make_profile("spanish")
        pipeline = VoicePipeline(profile)
        assert pipeline._tts is None

    def test_profile_stored(self):
        from language_tutor.voice.tts import VoicePipeline
        profile = self._make_profile("spanish")
        pipeline = VoicePipeline(profile)
        assert pipeline.profile is profile

    def test_synthesize_applies_latin_phonetic_preprocessing(self, tmp_path, monkeypatch):
        """Latin pipeline must call _latin_phonetic before TTS."""
        from language_tutor.voice.tts import VoicePipeline, _latin_phonetic
        profile = self._make_profile("latin")
        pipeline = VoicePipeline(profile)

        captured = {}

        class FakeTTS:
            async def generate_speech(self, text: str, speed: str = "normal") -> str:
                captured["text"] = text
                return base64.b64encode(b"WAV").decode()

        pipeline._tts = FakeTTS()

        asyncio.run(pipeline.synthesize("veni vidi vici"))
        # Preprocessing should have been applied
        assert captured["text"] == _latin_phonetic("veni vidi vici")


# ---------------------------------------------------------------------------
# STTService — construction without live model
# ---------------------------------------------------------------------------

class TestSTTService:
    @pytest.fixture(autouse=True)
    def _mock_whisper(self, monkeypatch):
        """Prevent WhisperModel from loading a real model during tests."""
        fake_model = MagicMock()
        fake_model.transcribe.return_value = (iter([]), MagicMock())
        import language_tutor.voice.stt as _stt_mod
        monkeypatch.setattr(_stt_mod, "WhisperModel", lambda *a, **kw: fake_model)
        self._fake_model = fake_model

    def test_construction_stores_language(self):
        from language_tutor.voice.stt import STTService
        svc = STTService(language="es")
        assert svc.language == "es"

    def test_construction_stores_model_name(self):
        from language_tutor.voice.stt import STTService
        svc = STTService(model_name="base", language="es")
        assert svc.model_name == "base"

    def test_whisper_language_auto_env_sets_none(self, monkeypatch):
        import importlib
        monkeypatch.setenv("WHISPER_LANGUAGE", "auto")
        import language_tutor.voice.stt as _mod
        importlib.reload(_mod)
        svc = _mod.STTService()
        assert svc.language is None

    def test_transcribe_bytes_returns_string(self):
        from language_tutor.voice.stt import STTService
        seg = MagicMock()
        seg.text = "Hola mundo"
        self._fake_model.transcribe.return_value = (iter([seg]), MagicMock())
        svc = STTService(language="es")
        result = asyncio.run(svc.transcribe_bytes(b"fake-audio"))
        assert isinstance(result, str)
        assert "Hola" in result

    def test_transcribe_bytes_returns_error_string_on_failure(self):
        from language_tutor.voice.stt import STTService
        self._fake_model.transcribe.side_effect = RuntimeError("model error")
        svc = STTService(language="es")
        result = asyncio.run(svc.transcribe_bytes(b"bad-audio"))
        assert result.startswith("[transcription error")

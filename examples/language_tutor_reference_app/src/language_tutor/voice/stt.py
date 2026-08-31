"""
Speech-to-Text Service

Wraps faster-whisper for async transcription.
Loaded once per process; runs synchronous inference in a thread pool
so the FastAPI event loop stays responsive.

Language selection:
  The `language` argument sets the Whisper decode language.
  For Latin ("la"), Whisper support exists but quality varies.
  Set WHISPER_LANGUAGE=auto in environment to use Whisper's automatic
  language detection instead of forcing Latin — often gives better results
  for Classical Latin text.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from faster_whisper import WhisperModel

from language_tutor.config import WHISPER_CONFIG


class STTService:
    """
    Async STT service backed by faster-whisper.

    Load once at startup, call transcribe_bytes() per request.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        language: Optional[str] = None,
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
    ) -> None:
        self.model_name = model_name or WHISPER_CONFIG["model"]
        self.device = device or WHISPER_CONFIG["device"]
        self.compute_type = compute_type or WHISPER_CONFIG["compute_type"]

        # Language resolution:
        #   1. WHISPER_LANGUAGE env var (set to "auto" for auto-detection)
        #   2. constructor argument
        #   3. default "es"
        # "auto" → None, which tells faster-whisper to detect the language.
        env_lang = os.environ.get("WHISPER_LANGUAGE", "").strip().lower()
        if env_lang == "auto":
            self.language = None  # auto-detect
        elif env_lang:
            self.language = env_lang
        else:
            self.language = language or "es"

        self.model = WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
            num_workers=1,
        )

        # One worker keeps CPU usage predictable during a live session
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt")

    async def transcribe_bytes(self, audio_data: bytes) -> str:
        """Transcribe raw audio bytes (WAV/OGG/WebM) and return text."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._transcribe_sync, audio_data)

    def _transcribe_sync(self, audio_data: bytes) -> str:
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_data)
                tmp_path = f.name

            segments, _info = self.model.transcribe(
                tmp_path,
                language=self.language,
                task="transcribe",
                beam_size=WHISPER_CONFIG["beam_size"],
                best_of=WHISPER_CONFIG["best_of"],
                temperature=WHISPER_CONFIG["temperature"],
                vad_filter=WHISPER_CONFIG["vad_filter"],
                compression_ratio_threshold=WHISPER_CONFIG["compression_ratio_threshold"],
                log_prob_threshold=WHISPER_CONFIG["log_prob_threshold"],
                no_speech_threshold=WHISPER_CONFIG["no_speech_threshold"],
                condition_on_previous_text=False,
                word_timestamps=False,
            )

            text = " ".join(seg.text for seg in segments).strip()
            return text if text else ""

        except Exception as e:
            return f"[transcription error: {e}]"
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

    def close(self) -> None:
        self._executor.shutdown(wait=False)

"""
VoicePipeline — Unified voice interface for Language Tutor

Wraps STTService (faster-whisper) and PiperTTSService (piper CLI) into a
single object keyed to a LanguageProfile. Handles:

  - Language-specific Whisper model configuration
  - Piper TTS synthesis with optional phonetic pre-processing for Latin
  - Latin Classical pronunciation mapping hook (to be expanded in Phase 4)

Usage:
    from language_tutor.voice.tts import VoicePipeline
    from language_tutor.config import get_language_profile

    pipeline = VoicePipeline(get_language_profile("spanish"))
    text = await pipeline.transcribe(audio_bytes)
    wav_b64 = await pipeline.synthesize("Hola, ¿cómo estás?")

Note on XTTS (Latin Phase 4):
    Latin is currently routed to Piper. When XTTS voice cloning is
    implemented, add an XTTSService class to this package and update
    _build_tts() to dispatch on profile.tts_backend == "xtts".
"""

from __future__ import annotations

from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from language_tutor.config import LanguageProfile


# ---------------------------------------------------------------------------
# Classical Latin phonetic pre-processor (stub — Phase 4)
# ---------------------------------------------------------------------------

def _latin_phonetic(text: str) -> str:
    """Apply Classical Latin pronunciation rules before TTS synthesis.

    Current scope: basic orthographic substitutions so that a generic TTS
    engine produces something closer to Classical rather than Church Latin.

    Planned Phase 4 additions:
      - Full CLTK G2P pipeline (v=/w/, c=/k/, ae=/ae̯/)
      - Fine-tuned Qwen3-TTS on male Classical Latin speakers
      - Voice cloning from family recordings for personal Latin tutor
    """
    # v → w phoneme (approximate via spelling; limited without a G2P pipeline)
    text = text.replace("v", "w").replace("V", "W")
    # c is always /k/ in Classical Latin — no substitution needed for piper
    # ae as a digraph — leave for full G2P implementation
    return text


# ---------------------------------------------------------------------------
# VoicePipeline
# ---------------------------------------------------------------------------

class VoicePipeline:
    """Unified STT + TTS pipeline for one language profile.

    Lazily initialises the underlying services on first use so that
    importing this module doesn't load Whisper or check for piper.

    Args:
        profile: LanguageProfile instance for the target language.
    """

    def __init__(self, profile: "LanguageProfile") -> None:
        self.profile = profile
        self._stt: Optional[object] = None
        self._tts: Optional[object] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes to text using faster-whisper.

        Returns an empty string (not an error string) when no speech
        is detected, so callers can distinguish silence from errors.
        """
        stt = self._get_stt()
        return await stt.transcribe_bytes(audio_bytes)

    async def synthesize(self, text: str, speed: str = "normal") -> Optional[str]:
        """Synthesise text to a base64-encoded WAV string via piper.

        Returns None if no piper model is available, so callers can
        degrade gracefully to text-only without raising.

        Applies Classical Latin phonetic pre-processing when
        profile.needs_phonetic_mapping is True.
        """
        if self.profile.needs_phonetic_mapping:
            text = _latin_phonetic(text)

        tts = self._get_tts()
        if tts is None:
            return None
        return await tts.generate_speech(text, speed=speed)

    async def full_cycle(
        self,
        audio_bytes: bytes,
        speed: str = "normal",
    ) -> Tuple[str, Optional[str]]:
        """Convenience: transcribe audio → return (transcript, None).

        TTS synthesis is intentionally separated — the caller should first
        generate a text response (via the LLM), then call synthesize() on
        the result. This method exists for future streaming pipelines.

        Returns:
            (transcript, None) — second element reserved for future use.
        """
        transcript = await self.transcribe(audio_bytes)
        return transcript, None

    # ------------------------------------------------------------------
    # Lazy initialisation
    # ------------------------------------------------------------------

    def _get_stt(self):
        if self._stt is None:
            from language_tutor.voice.stt import STTService
            self._stt = STTService(
                language=self.profile.whisper_language or "es",
            )
        return self._stt

    def _get_tts(self):
        if self._tts is None:
            try:
                from language_tutor.voice.piper_tts import PiperTTSService
                self._tts = PiperTTSService()
            except RuntimeError:
                # No piper model found — TTS disabled for this session
                self._tts = False   # sentinel: tried and failed
        return self._tts if self._tts is not False else None

    def close(self) -> None:
        """Release resources held by the STT service."""
        if self._stt is not None:
            try:
                self._stt.close()
            except Exception:
                pass
            self._stt = None

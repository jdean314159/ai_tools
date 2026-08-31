"""
Pronunciation Scorer — Phase 2 Voice Feature

Scores pronunciation accuracy by comparing user audio against expected text.
Uses two complementary signals:

  1. Phonetic accuracy — Whisper transcription vs expected text
     (Levenshtein ratio via difflib.SequenceMatcher)

  2. Fluency — timing consistency from word-level timestamps
     (variance in word duration + pause length)

  3. Acoustic similarity (optional) — MFCC cosine distance when a
     reference audio recording is provided.

Dependencies:
  pip install faster-whisper --break-system-packages
  pip install librosa scipy --break-system-packages   # for acoustic similarity

Usage:
    from language_tutor.drills.pronunciation import PronunciationScorer

    scorer = PronunciationScorer(language="es")
    result = await scorer.score(audio_bytes, "Me llamo Jeff y vivo en California")
    print(result["score"], result["feedback"])

Adapted from spanish_tutor/services/pronunciation_scorer.py.
"""

from __future__ import annotations

import asyncio
import tempfile
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class PronunciationScorer:
    """Async pronunciation scorer backed by faster-whisper.

    Loaded once per session; transcription runs in a thread pool so the
    FastAPI event loop stays responsive.

    Args:
        language: ISO language code ("es", "la") for Whisper.
        whisper_model: faster-whisper model name (default "small").
        device: "cuda" or "cpu".
        compute_type: "int8", "float16", etc.
    """

    def __init__(
        self,
        language: str = "es",
        whisper_model: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        self.language = language
        self._whisper_model_name = whisper_model
        self._device = device
        self._compute_type = compute_type
        self._model = None  # lazy-loaded on first call

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self._whisper_model_name,
                device=self._device,
                compute_type=self._compute_type,
                num_workers=1,
            )
        return self._model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def score(
        self,
        user_audio: bytes,
        expected_text: str,
        reference_audio: Optional[bytes] = None,
    ) -> Dict:
        """Score pronunciation asynchronously.

        Returns:
            {
                "score":            0–100  (weighted composite),
                "phonetic_accuracy":0–100  (text similarity),
                "fluency_score":    0–100  (timing consistency),
                "acoustic_score":   0–100  (MFCC similarity; 100 if no reference),
                "feedback":         str,
                "detected_text":    str    (what Whisper heard),
                "expected_text":    str,
                "word_timestamps":  list,
            }
        """
        return await asyncio.to_thread(self._score_sync, user_audio, expected_text, reference_audio)

    # ------------------------------------------------------------------
    # Synchronous implementation
    # ------------------------------------------------------------------

    def _score_sync(
        self,
        user_audio: bytes,
        expected_text: str,
        reference_audio: Optional[bytes],
    ) -> Dict:
        user_text, word_timestamps = self._transcribe_with_timestamps(user_audio)
        phonetic = self._phonetic_accuracy(user_text, expected_text)
        fluency = self._fluency_score(word_timestamps)
        acoustic = 100.0
        if reference_audio:
            acoustic = self._acoustic_similarity(user_audio, reference_audio)

        overall = phonetic * 0.5 + fluency * 0.3 + acoustic * 0.2
        feedback = self._generate_feedback(overall, phonetic, fluency, user_text, expected_text)

        return {
            "score": round(overall, 1),
            "phonetic_accuracy": round(phonetic, 1),
            "fluency_score": round(fluency, 1),
            "acoustic_score": round(acoustic, 1),
            "feedback": feedback,
            "detected_text": user_text,
            "expected_text": expected_text,
            "word_timestamps": word_timestamps,
        }

    def _transcribe_with_timestamps(self, audio_bytes: bytes) -> Tuple[str, List[Dict]]:
        """Transcribe audio, returning (text, word_timing_list)."""
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_bytes)
                tmp_path = f.name

            model = self._get_model()
            segments, _ = model.transcribe(
                tmp_path,
                language=self.language,
                word_timestamps=True,
                beam_size=5,
            )

            text_parts: List[str] = []
            word_timings: List[Dict] = []
            for segment in segments:
                if hasattr(segment, "words") and segment.words:
                    for w in segment.words:
                        text_parts.append(w.word.strip())
                        word_timings.append(
                            {
                                "word": w.word.strip(),
                                "start": round(w.start, 3),
                                "end": round(w.end, 3),
                                "probability": round(w.probability, 3),
                            }
                        )
            return " ".join(text_parts).strip(), word_timings

        except Exception as e:
            return f"[transcription error: {e}]", []
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

    def _phonetic_accuracy(self, user_text: str, expected_text: str) -> float:
        """Levenshtein ratio on word lists, normalised to 0–100."""
        u_words = user_text.lower().split()
        e_words = expected_text.lower().split()
        return SequenceMatcher(None, e_words, u_words).ratio() * 100.0

    def _fluency_score(self, word_timestamps: List[Dict]) -> float:
        """Score fluency from timing data.

        Penalises:
          - High variance in word duration (choppy delivery)
          - Long inter-word pauses (> 0.5 s)
          - Very slow average word duration (> 0.8 s/word)
        """
        if len(word_timestamps) < 2:
            return 100.0

        import statistics

        durations = [w["end"] - w["start"] for w in word_timestamps]
        pauses = [
            word_timestamps[i + 1]["start"] - word_timestamps[i]["end"]
            for i in range(len(word_timestamps) - 1)
        ]

        score = 100.0
        try:
            duration_stdev = statistics.stdev(durations)
        except statistics.StatisticsError:
            duration_stdev = 0.0
        if duration_stdev > 0.3:
            score -= 20.0
        if pauses and max(pauses) > 0.5:
            score -= min(30.0, max(pauses) * 15)
        avg_dur = sum(durations) / len(durations)
        if avg_dur > 0.8:
            score -= 20.0
        return max(0.0, score)

    def _acoustic_similarity(self, user_audio: bytes, reference_audio: bytes) -> float:
        """MFCC cosine similarity, 0–100.

        Requires librosa and scipy.  Returns 100.0 if they are not installed
        so the absence of optional deps doesn't break scoring.
        """
        try:
            import numpy as np
            import librosa
            from scipy.spatial.distance import cosine
        except ImportError:
            return 100.0

        def _mfcc(audio_bytes: bytes, n_mfcc: int = 13) -> "np.ndarray":
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_bytes)
                tmp = f.name
            try:
                y, sr = librosa.load(tmp, sr=16000)
                return np.mean(librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc), axis=1)
            finally:
                Path(tmp).unlink(missing_ok=True)

        try:
            user_mfcc = _mfcc(user_audio)
            ref_mfcc = _mfcc(reference_audio)
            similarity = 1.0 - cosine(user_mfcc.flatten(), ref_mfcc.flatten())
            return float(max(0.0, min(100.0, similarity * 100.0)))
        except Exception:
            return 100.0

    def _generate_feedback(
        self,
        overall: float,
        phonetic: float,
        fluency: float,
        user_text: str,
        expected_text: str,
    ) -> str:
        """Spanish-language feedback messages with English fallback."""
        if overall >= 90:
            return "¡Excelente pronunciación! Muy claro y natural."
        if overall >= 75:
            parts = ["¡Muy bien!"]
            if phonetic < 80:
                parts.append("Revisa algunas palabras.")
            if fluency < 80:
                parts.append("Intenta hablar un poco más fluido.")
            return " ".join(parts)
        if overall >= 60:
            parts = ["Buen intento."]
            if phonetic < 70:
                # Highlight first differing word
                u_words = user_text.lower().split()
                e_words = expected_text.lower().split()
                errors = [
                    e_words[i]
                    for i in range(min(len(e_words), len(u_words)))
                    if i >= len(u_words) or u_words[i] != e_words[i]
                ][:3]
                if errors:
                    parts.append(f"Practica: {', '.join(errors)}.")
            if fluency < 70:
                parts.append("Habla más fluido, sin pausas largas.")
            return " ".join(parts)
        return f"Sigue practicando. Intenta decir: '{expected_text}'"

    def close(self) -> None:
        """Release Whisper model."""
        self._model = None

"""
Piper TTS Service

Calls the piper binary as a subprocess to synthesise speech.
Returns base64-encoded WAV so the caller can embed it directly in JSON.

Model path resolution order:
  1. PIPER_MODEL_PATH env var (must point to the .onnx file)
  2. ~/ai_tools/models/piper/<first .onnx file found>
  3. RuntimeError — model not found
"""

from __future__ import annotations

import asyncio
import base64
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from language_tutor.config import PIPER_CONFIG


def _find_model() -> Path:
    """Locate a piper voice model file.

    Search order:
    1. PIPER_MODEL_PATH env var
    2. ./piper/ directory (project-local — portable across machines)
    3. ~/ai_tools/models/piper/
    """
    env_path = os.environ.get("PIPER_MODEL_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p
        raise RuntimeError(f"PIPER_MODEL_PATH set but file not found: {env_path}")

    # Project-local piper directory (language_tutor/piper/)
    project_piper = Path(__file__).parent.parent.parent / "piper"
    if project_piper.is_dir():
        models = sorted(project_piper.glob("**/*.onnx"))
        if models:
            return models[0]

    # Fallback: ~/ai_tools/models/piper/
    search_dir = Path.home() / "ai_tools" / "models" / "piper"
    if search_dir.is_dir():
        models = sorted(search_dir.glob("**/*.onnx"))
        if models:
            return models[0]

    raise RuntimeError(
        "No piper model found. Place a .onnx file in ./piper/, "
        "set PIPER_MODEL_PATH, or put it in ~/ai_tools/models/piper/"
    )


class PiperTTSService:
    """
    Async TTS service backed by the piper CLI.

    generate_speech() runs the subprocess off the event loop so FastAPI
    stays responsive during synthesis.
    """

    def __init__(self, model_path: Optional[Path] = None) -> None:
        self.model_path = model_path or _find_model()
        self._speed_map: dict = PIPER_CONFIG["speed_map"]
        self._timeout: int = PIPER_CONFIG["timeout"]

    async def generate_speech(self, text: str, speed: str = "normal") -> str:
        """
        Synthesise *text* and return a base64-encoded WAV string.

        speed: "slow" | "normal" | "fast"
        Raises RuntimeError if piper binary is missing or returns non-zero.
        """
        return await asyncio.to_thread(self._synthesise_sync, text, speed)

    def _synthesise_sync(self, text: str, speed: str) -> str:
        length_scale = self._speed_map.get(speed, self._speed_map["normal"])

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out_path = f.name

        try:
            result = subprocess.run(
                [
                    "piper",
                    "--model",
                    str(self.model_path),
                    "--output_file",
                    out_path,
                    "--length_scale",
                    str(length_scale),
                ],
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=self._timeout,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"piper exited {result.returncode}: "
                    f"{result.stderr.decode(errors='replace')[:200]}"
                )
            return base64.b64encode(Path(out_path).read_bytes()).decode()
        finally:
            Path(out_path).unlink(missing_ok=True)

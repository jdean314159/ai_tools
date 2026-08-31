#!/usr/bin/env python3
"""
Pre-Flight System Check

Validates system configuration before starting the language tutor.
Checks GPU, Ollama server, required models, engram, and config.

Usage:
    python -m language_tutor.preflight_check
    python -m language_tutor.preflight_check --quick
    python -m language_tutor.preflight_check --start-ollama
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List


CONFIG_PATH = Path.home() / ".language_tutor_config.json"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


class PreFlightCheck:
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def run(self, quick: bool = False, start_ollama: bool = False) -> bool:
        print("\n" + "=" * 60)
        print("LANGUAGE TUTOR PRE-FLIGHT CHECK")
        print("=" * 60 + "\n")

        checks = [
            ("GPU / CUDA", self.check_gpu),
            ("Python dependencies", self.check_dependencies),
            ("Engram library", self.check_engram),
            ("Configuration", self.check_config),
        ]

        if not quick:
            checks += [
                ("Ollama server", lambda: self.check_ollama(start_ollama)),
                ("Ollama models", self.check_ollama_models),
            ]

        all_passed = True
        for name, fn in checks:
            print(f"Checking {name}...")
            try:
                passed = fn()
            except Exception as exc:
                self.errors.append(f"{name} check raised: {exc}")
                passed = False
            status = "✓" if passed else "✗"
            print(f"   {status} {name}\n")
            if not passed:
                all_passed = False

        print("=" * 60)
        if all_passed and not self.errors:
            print("✓ ALL CHECKS PASSED — system ready\n")
        else:
            print("✗ CHECKS FAILED\n")

        if self.errors:
            print("Errors:")
            for e in self.errors:
                print(f"  • {e}")
            print()

        if self.warnings:
            print("Warnings:")
            for w in self.warnings:
                print(f"  • {w}")
            print()

        print("=" * 60 + "\n")
        return all_passed and not self.errors

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def check_gpu(self) -> bool:
        try:
            import torch
        except ImportError:
            self.warnings.append("PyTorch not installed — cannot verify GPU")
            return True

        if not torch.cuda.is_available():
            self.warnings.append("No CUDA GPU detected — CPU-only mode will be slow")
            return True

        name = torch.cuda.get_device_name(0)
        props = torch.cuda.get_device_properties(0)
        vram_gb = props.total_memory / (1024**3)
        free_gb = (props.total_memory - torch.cuda.memory_allocated(0)) / (1024**3)

        print(f"   GPU  : {name}")
        print(f"   VRAM : {vram_gb:.1f} GB total, {free_gb:.1f} GB free")

        if free_gb < 8.0:
            self.warnings.append(
                f"Only {free_gb:.1f} GB VRAM free — close other GPU processes if models fail to load"
            )

        return True

    def check_dependencies(self) -> bool:
        required = {
            "fastapi": "API server",
            "uvicorn": "ASGI server",
            "pydantic": "Data validation",
            "httpx": "HTTP client",
            "chromadb": "Episodic memory (engram[episodic])",
            "sentence_transformers": "Embeddings (engram[episodic])",
            "kuzu": "Semantic memory (engram[semantic])",
            "sklearn": "Graph extraction (scikit-learn)",
        }
        optional = {
            "torch": "Neural memory layer / GPU acceleration",
            "tiktoken": "Accurate token counting",
            "faster_whisper": "Speech-to-text / voice input (Phase 2)",
        }

        missing = []
        for mod, desc in required.items():
            try:
                __import__(mod)
            except ImportError:
                missing.append(f"{mod}  ({desc})")

        for mod, desc in optional.items():
            try:
                __import__(mod)
                if mod == "faster_whisper":
                    print("   faster-whisper : ✓")
                    whisper_lang = os.getenv("WHISPER_LANGUAGE", "")
                    if whisper_lang == "auto":
                        print("   WHISPER_LANGUAGE: auto-detect mode")
                    elif whisper_lang:
                        print(f"   WHISPER_LANGUAGE: {whisper_lang}")
                    else:
                        self.warnings.append(
                            "WHISPER_LANGUAGE not set. For Latin sessions, "
                            "consider: export WHISPER_LANGUAGE=auto"
                        )
            except ImportError:
                self.warnings.append(f"Optional package not installed: {mod} — {desc}")

        if missing:
            self.errors.append("Missing required packages:")
            for pkg in missing:
                self.errors.append(f"  pip install {pkg.split()[0]}")
            return False

        # Check piper binary
        import shutil

        project_piper = Path(__file__).parent.parent / "piper" / "piper"
        piper_path = shutil.which("piper") or (
            str(project_piper) if project_piper.exists() else None
        )
        if piper_path:
            print(f"   piper binary   : ✓  {piper_path}")
        else:
            self.warnings.append(
                "piper binary not found in PATH, ./piper/, or ~/ai_tools/models/piper/ — "
                "TTS will be disabled. Download from: "
                "https://github.com/rhasspy/piper/releases"
            )

        # Check piper voice model
        piper_model_env = os.getenv("PIPER_MODEL_PATH")
        if piper_model_env:
            if Path(piper_model_env).exists():
                print(f"   piper model    : ✓  {piper_model_env}")
            else:
                self.warnings.append(f"PIPER_MODEL_PATH set but file not found: {piper_model_env}")
        else:
            # Search project piper dir first, then ~/ai_tools/models/piper/
            project_piper_dir = Path(__file__).parent.parent / "piper"
            search_dirs = [project_piper_dir, Path.home() / "ai_tools" / "models" / "piper"]
            models = []
            for d in search_dirs:
                if d.is_dir():
                    models = list(d.glob("**/*.onnx"))
                    if models:
                        break
            if models:
                print(f"   piper model    : ✓  {models[0].name} (+{len(models) - 1} more)")
            else:
                self.warnings.append(
                    "No piper voice model (.onnx) found in ./piper/ or ~/ai_tools/models/piper/ — "
                    "TTS will be disabled. Set PIPER_MODEL_PATH or place model there."
                )

        print(f"   ✓ {len(required)} required packages present")
        return True

    def check_engram(self) -> bool:
        try:
            import engram

            print(f"   engram {engram.__version__}")
        except ImportError:
            self.errors.append("engram not installed — run: pip install -e /path/to/engram")
            return False

        # Verify key submodules load
        try:
            pass
        except Exception as exc:
            self.errors.append(f"engram import error: {exc}")
            return False

        # Engine loading goes through llm_engines, not engram.engine — verify
        # the factory is importable so engine setup will succeed at runtime.
        try:
            from llm_engines.factory import EngineFactory  # noqa: F401
        except Exception as exc:
            self.errors.append(f"llm_engines import error: {exc}")
            return False

        return True

    def check_config(self) -> bool:
        if not CONFIG_PATH.exists():
            self.errors.append(
                f"No config found at {CONFIG_PATH} — run setup wizard: "
                "python -m language_tutor.setup_wizard"
            )
            return False

        try:
            config = json.loads(CONFIG_PATH.read_text())
        except Exception as exc:
            self.errors.append(f"Config file unreadable: {exc}")
            return False

        strategy_name = config.get("strategy")
        if not strategy_name:
            self.errors.append("Config missing 'strategy' key — re-run setup wizard")
            return False

        print(f"   Strategy : {strategy_name}")

        # Check API keys based on strategy
        from language_tutor.hardware_strategy import STRATEGIES

        strategy = STRATEGIES.get(strategy_name)
        if strategy:
            for role in ("planner", "executor"):
                cfg = strategy.get(role, {})
                engine = cfg.get("engine", "")
                if engine == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
                    self.errors.append(f"Strategy '{strategy_name}' requires ANTHROPIC_API_KEY")
                    return False
                if engine == "gemini" and not os.getenv("GOOGLE_API_KEY"):
                    self.errors.append(
                        f"Strategy '{strategy_name}' requires GOOGLE_API_KEY — "
                        "get a free key at https://aistudio.google.com/apikey "
                        "then: export GOOGLE_API_KEY='your-key'"
                    )
                    return False
                if engine == "anthropic":
                    print("   Anthropic API key : ✓ found")
                if engine == "gemini":
                    print("   Google API key    : ✓ found")
                if engine == "llama_cpp":
                    gguf = cfg.get("gguf_path") or os.getenv("LLAMA_MODEL_PATH", "")
                    if gguf and not Path(gguf).exists():
                        self.warnings.append(f"LLAMA_MODEL_PATH not found: {gguf}")
                    elif not gguf:
                        self.warnings.append(
                            "LLAMA_MODEL_PATH not set — set it before starting llama-server"
                        )

        return True

    def check_ollama(self, start_if_down: bool = False) -> bool:
        import urllib.request
        import urllib.error

        url = f"{OLLAMA_BASE_URL}/api/tags"

        def _ping() -> bool:
            try:
                with urllib.request.urlopen(url, timeout=3) as r:
                    return r.status == 200
            except Exception:
                return False

        if _ping():
            print(f"   Ollama running at {OLLAMA_BASE_URL}")
            return True

        if start_if_down:
            print("   Ollama not running — attempting to start...")
            try:
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                self.errors.append(
                    "ollama binary not found — install from https://ollama.com/download"
                )
                return False

            # Wait up to 10 seconds
            for _ in range(10):
                time.sleep(1)
                if _ping():
                    print(f"   ✓ Ollama started at {OLLAMA_BASE_URL}")
                    return True

            self.errors.append("Ollama did not start within 10 seconds")
            return False

        self.errors.append(
            f"Ollama not reachable at {OLLAMA_BASE_URL} — "
            "start it with:  ollama serve  "
            "(or re-run with --start-ollama)"
        )
        return False

    def check_ollama_models(self) -> bool:
        """Verify that models referenced in the config are pulled."""
        if not CONFIG_PATH.exists():
            return True  # config check already failed

        try:
            config = json.loads(CONFIG_PATH.read_text())
        except Exception:
            return True

        from language_tutor.hardware_strategy import STRATEGIES

        strategy = STRATEGIES.get(config.get("strategy", ""))
        if not strategy:
            return True

        needed: List[str] = []
        for role in ("planner", "executor"):
            cfg = strategy.get(role, {})
            if cfg.get("engine") == "ollama":
                needed.append(cfg["model"])

        if not needed:
            print("   No Ollama models required by this strategy")
            return True

        # Fetch pulled models
        import urllib.request
        import json as _json

        try:
            with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=5) as r:
                data = _json.loads(r.read())
            pulled = {m["name"] for m in data.get("models", [])}
        except Exception as exc:
            self.warnings.append(f"Could not fetch Ollama model list: {exc}")
            return True

        missing = [m for m in needed if m not in pulled]
        if missing:
            for m in missing:
                self.errors.append(f"Ollama model not pulled: {m} — run:  ollama pull {m}")
            return False

        for m in needed:
            print(f"   ✓ {m}")
        return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Language tutor pre-flight check")
    parser.add_argument("--quick", action="store_true", help="Skip Ollama and model checks")
    parser.add_argument(
        "--start-ollama",
        action="store_true",
        help="Start ollama serve automatically if not running",
    )
    args = parser.parse_args()

    checker = PreFlightCheck()
    ok = checker.run(quick=args.quick, start_ollama=args.start_ollama)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env bash
# Language Tutor — startup script
# Usage:
#   ./start.sh              — web UI on port 8080
#   ./start.sh --setup      — run setup wizard (choose/change strategy)
#   ./start.sh --preflight  — run preflight check only
#   ./start.sh --cli        — command-line interactive session
#   ./start.sh --test       — quick smoke test (no UI)
#   ./start.sh --integration-test — run Engram integration tests

set -euo pipefail
cd "$(dirname "$0")"

# ── Environment ──────────────────────────────────────────────────────
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"

# Unload Ollama models immediately after use so planner and executor
# don't compete for VRAM (27b + 9b together exceed 24GB).
export OLLAMA_KEEP_ALIVE=0

# Add project-local piper to PATH if present (portable across machines)
if [ -f "$(pwd)/piper/piper" ]; then
    export PATH="$(pwd)/piper:$PATH"
fi

# Uncomment and set for Gemini strategies (free tier at aistudio.google.com)
# export GOOGLE_API_KEY="your-key-here"

# Uncomment and set for OpenAI strategies
# export OPENAI_API_KEY="your-key-here"

# Uncomment and set for Anthropic/Claude strategies
# export ANTHROPIC_API_KEY="your-key-here"

# Uncomment to override Whisper language (set to "" for auto-detect)
# export WHISPER_LANGUAGE=""

# Uncomment to restrict CORS (default: localhost:8080)
# export CORS_ORIGINS="http://localhost:8080,http://192.168.1.10:8080"

# Uncomment to set a specific piper voice model
# export PIPER_MODEL_PATH="$HOME/ai_tools/models/piper/es_MX-claude-high.onnx"

# ── Argument handling ────────────────────────────────────────────────
case "${1:-}" in
  --setup)
    python3 -c "
from language_tutor.hardware_strategy import setup_wizard
setup_wizard()
"
    ;;
  --preflight)
    python3 -m language_tutor.preflight_check
    ;;
  --cli)
    python3 main_example.py
    ;;
  --test)
    python3 main_example.py --test
    ;;
  --integration-test)
    python3 tests/test_engram_integration.py --verbose
    ;;
  *)
    echo "Starting Language Tutor web server on http://localhost:8080"
    echo "Press Ctrl+C to stop."
    echo ""
    python3 -m uvicorn language_tutor.app:app \
      --host 0.0.0.0 \
      --port 8080 \
      --log-level info
    ;;
esac

#!/usr/bin/env bash
# run_both_backends.sh
# Runs the eval harness against both engram and engram_lite, then compares.
#
# Usage:
#   cd ~/ai_tools/engram/tests/eval
#   bash run_both_backends.sh
#
# Requires:
#   - Ollama running with nomic-embed-text pulled
#   - ANTHROPIC_API_KEY set

set -e

EVAL_DIR="$(cd "$(dirname "$0")" && pwd)"
CORPUS_CACHE="${EVAL_DIR}/eval_corpus.json"
RESULTS_ENGRAM="${EVAL_DIR}/eval_results_engram"
RESULTS_LITE="${EVAL_DIR}/eval_results_lite"

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "ERROR: ANTHROPIC_API_KEY not set"
    exit 1
fi

if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "ERROR: Ollama not running at localhost:11434"
    exit 1
fi

echo "============================================================"
echo "  Engram Memory Eval — Dual Backend Comparison"
echo "============================================================"
echo ""

# ── Run 1: Full engram ────────────────────────────────────────────────────────
echo ">>> Run 1: Full engram"
echo "    Output: $RESULTS_ENGRAM"
echo ""

BACKEND=engram python run_eval.py \
    --corpus-cache "$CORPUS_CACHE" \
    --output "$RESULTS_ENGRAM"

echo ""
echo ">>> Run 1 complete."
echo ""

# ── Run 2: engram_lite ────────────────────────────────────────────────────────
echo ">>> Run 2: engram_lite"
echo "    Output: $RESULTS_LITE"
echo "    Corpus: reusing cached corpus from Run 1"
echo ""

BACKEND=engram_lite python run_eval.py \
    --corpus-cache "$CORPUS_CACHE" \
    --output "$RESULTS_LITE" \
    --skip-generate

echo ""
echo ">>> Run 2 complete."
echo ""

# ── Comparison ────────────────────────────────────────────────────────────────
echo "============================================================"
echo "  Comparison"
echo "============================================================"

python compare_backends.py \
    --engram      "${RESULTS_ENGRAM}/metrics.json" \
    --engram-lite "${RESULTS_LITE}/metrics.json"

echo ""
echo "Done. Full results:"
echo "  engram:      $RESULTS_ENGRAM"
echo "  engram_lite: $RESULTS_LITE"
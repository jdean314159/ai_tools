#!/bin/bash
# Verify all tool binaries work correctly
# Usage: ./scripts/verify-binaries.sh [expected-version]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
EXPECTED_VERSION="${1:-}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Verifying All Tool Binaries"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ -n "$EXPECTED_VERSION" ]; then
  echo "Expected version: $EXPECTED_VERSION"
  echo ""
fi

cd "$ROOT_DIR"

TOTAL_BINARIES=0
SUCCESS_BINARIES=0
FAILED_BINARIES=()

# Find all locally built binaries in ~/.claude/bin
if [ -d "$HOME/.claude/bin" ]; then
  echo "📦 Verifying locally built tools in ~/.claude/bin"
  echo ""

  for binary in "$HOME/.claude/bin"/*; do
    if [ -f "$binary" ] && [ -x "$binary" ]; then
      BINARY_NAME=$(basename "$binary")
      TOTAL_BINARIES=$((TOTAL_BINARIES + 1))

      echo "   Testing: $BINARY_NAME"

      # Test if binary runs
      if OUTPUT=$("$binary" --version 2>&1); then
        echo "      ✅ Runs: $OUTPUT"

        # Check version if specified
        if [ -n "$EXPECTED_VERSION" ]; then
          if echo "$OUTPUT" | grep -q "$EXPECTED_VERSION"; then
            echo "      ✅ Version matches"
            SUCCESS_BINARIES=$((SUCCESS_BINARIES + 1))
          else
            echo "      ❌ Version mismatch (expected: $EXPECTED_VERSION)"
            FAILED_BINARIES+=("$BINARY_NAME")
          fi
        else
          SUCCESS_BINARIES=$((SUCCESS_BINARIES + 1))
        fi
      else
        echo "      ❌ Failed to run"
        FAILED_BINARIES+=("$BINARY_NAME")
      fi
    fi
  done
  echo ""
else
  echo "⚠️  No binaries found at ~/.claude/bin"
  echo "   Run the install script first to build tools locally"
  echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Verification Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Total binaries: $TOTAL_BINARIES"
echo "✅ Passed: $SUCCESS_BINARIES"
echo "❌ Failed: ${#FAILED_BINARIES[@]}"
echo ""

if [ ${#FAILED_BINARIES[@]} -gt 0 ]; then
  echo "Failed binaries:"
  for binary in "${FAILED_BINARIES[@]}"; do
    echo "  - $binary"
  done
  echo ""
  exit 1
fi

echo "✅ All binaries verified successfully!"

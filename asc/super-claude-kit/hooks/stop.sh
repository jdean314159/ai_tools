#!/bin/bash

# Stop Hook (Pure Bash - WSL Compatible)
# Runs after each response - quality check
# - Suggests logging discoveries if file access is high but discoveries are low
#
# suppressOutput is in settings.json, so:
# - Normal case: exit silently
# - Quality tip: output plain text (like original)

# Suppress stderr
exec 2>/dev/null

# Get session info
WORKER_PROFILE="${CLAUDE_WORKER_PROFILE:-default}"
SESSION_ID="${CLAUDE_SESSION_ID:-$WORKER_PROFILE}"
SESSION_DIR=".claude/sessions/$SESSION_ID"
TIP_MARKER="$SESSION_DIR/quality_tip_shown.marker"

# Skip if tip already shown this session
[ -f "$TIP_MARKER" ] && exit 0

# Count file accesses and discoveries
FILE_COUNT=0
DISCOVERY_COUNT=0

if [ -f "$SESSION_DIR/file_access.log" ]; then
  FILE_COUNT=$(wc -l < "$SESSION_DIR/file_access.log" 2>/dev/null || echo "0")
fi

if [ -f "$SESSION_DIR/discoveries.log" ]; then
  DISCOVERY_COUNT=$(wc -l < "$SESSION_DIR/discoveries.log" 2>/dev/null || echo "0")
fi

# Quality check: 3+ files accessed but 0 discoveries
if [ "$FILE_COUNT" -ge 3 ] && [ "$DISCOVERY_COUNT" -eq 0 ]; then
  # Mark tip as shown
  touch "$TIP_MARKER"

  # Output plain text tip (like original stop.sh)
  echo ""
  echo "[QUALITY TIP] Accessed $FILE_COUNT files but logged 0 discoveries"
  echo "Consider: ./.claude/hooks/log-discovery.sh \"<category>\" \"<finding>\""
  echo ""
  exit 0
fi

# Normal case - exit silently
exit 0

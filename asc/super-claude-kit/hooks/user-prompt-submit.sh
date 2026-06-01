#!/bin/bash
# User Prompt Submit Hook - Minimal version
# Handles capsule refresh on subsequent prompts with multi-worker support
#
# Since suppressOutput: true is in settings.json:
# - Normal case: exit silently (no output)
# - Context injection: output JSON only when capsule changed

# Suppress stderr
exec 2>/dev/null

WORKER_PROFILE="${CLAUDE_WORKER_PROFILE:-default}"
SESSION_ID="${CLAUDE_SESSION_ID:-$WORKER_PROFILE}"
SESSION_DIR=".claude/sessions/$SESSION_ID"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$SESSION_DIR" 2>/dev/null

# Increment message count
MSG_FILE="$SESSION_DIR/message_count.txt"
if [ -f "$MSG_FILE" ]; then
  COUNT=$(($(cat "$MSG_FILE") + 1))
else
  COUNT=1
fi
echo "$COUNT" > "$MSG_FILE"

# Track marker for context injection
MARKER="$SESSION_DIR/context_injected.marker"

# First message - SessionStart already handled everything
if [ "$COUNT" -eq 1 ]; then
  [ ! -f "$MARKER" ] && date +%s > "$MARKER"
  exit 0
fi

# Subsequent messages - check if capsule refresh is needed
CAPSULE_UPDATE=""
if [ -f "$SCRIPT_DIR/inject-capsule.sh" ]; then
  CAPSULE_UPDATE=$(bash "$SCRIPT_DIR/inject-capsule.sh" 2>/dev/null)
fi

# If no update needed, exit silently
if [ -z "$CAPSULE_UPDATE" ]; then
  exit 0
fi

# Capsule changed - inject updated context
python3 -c "
import json
import sys

capsule = sys.stdin.read().strip()
if not capsule:
    sys.exit(0)

print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'UserPromptSubmit',
        'additionalContext': capsule
    }
}))
" <<< "$CAPSULE_UPDATE" 2>/dev/null

exit 0

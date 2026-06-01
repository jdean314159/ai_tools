#!/bin/bash
# Restore Capsule from Previous Session
# Loads persisted state if session was recent (<24 hours)
#
# IMPORTANT: This script outputs to JSON format for SessionStart hooks,
# or silently exits. Plain text output corrupts Claude Code UI.

# Redirect stderr to log file
exec 2>>.claude/hook-errors.log

PERSIST_FILE=".claude/capsule_persist.json"
CURRENT_TIME=$(date +%s 2>/dev/null || echo "0")
TWENTY_FOUR_HOURS=$((24 * 60 * 60))

# Check if persistence file exists
if [ ! -f "$PERSIST_FILE" ]; then
  exit 0  # No previous session to restore
fi

# Check if previous session was recent
LAST_SESSION_TIME=$(python3 -c "import json; data = json.load(open('$PERSIST_FILE')); print(data['last_session']['ended_at'])" 2>/dev/null || echo "0")
TIME_SINCE_SESSION=$((CURRENT_TIME - LAST_SESSION_TIME))

if [ "$TIME_SINCE_SESSION" -gt "$TWENTY_FOUR_HOURS" ]; then
  # Session too old - skip restore
  exit 0
fi

# Build restoration context for JSON output
RESTORE_CONTEXT=""

# Convert time since to human readable
if [ "$TIME_SINCE_SESSION" -lt 3600 ]; then
  TIME_STR="$((TIME_SINCE_SESSION / 60))m ago"
elif [ "$TIME_SINCE_SESSION" -lt 86400 ]; then
  TIME_STR="$((TIME_SINCE_SESSION / 3600))h ago"
else
  TIME_STR="$((TIME_SINCE_SESSION / 86400))d ago"
fi

# Get previous session info
PREV_DURATION=$(python3 -c "import json; data = json.load(open('$PERSIST_FILE')); print(data['last_session']['duration_seconds'])" 2>/dev/null || echo "0")
PREV_BRANCH=$(python3 -c "import json; data = json.load(open('$PERSIST_FILE')); print(data['last_session']['branch'])" 2>/dev/null || echo "unknown")

if [ "$PREV_DURATION" -lt 60 ]; then
  DUR_STR="${PREV_DURATION}s"
elif [ "$PREV_DURATION" -lt 3600 ]; then
  DUR_STR="$((PREV_DURATION / 60))m"
else
  DUR_STR="$((PREV_DURATION / 3600))h $((PREV_DURATION % 3600 / 60))m"
fi

# Build context string
RESTORE_CONTEXT="Previous session: $DUR_STR on $PREV_BRANCH ($TIME_STR)"

# Get discoveries summary
DISCOVERIES_SUMMARY=$(python3 << 'PYTHON_SCRIPT' 2>/dev/null || echo ""
import json
import sys

try:
    with open('.claude/capsule_persist.json', 'r') as f:
        data = json.load(f)

    discoveries = data.get('discoveries', [])
    if discoveries:
        items = []
        for disc in discoveries[:3]:  # Top 3
            category = disc.get('category', 'unknown')
            content = disc.get('content', '')[:50]
            items.append(f"[{category}] {content}")
        print("; ".join(items))
except:
    pass
PYTHON_SCRIPT
)

if [ -n "$DISCOVERIES_SUMMARY" ]; then
  RESTORE_CONTEXT="$RESTORE_CONTEXT | Discoveries: $DISCOVERIES_SUMMARY"
fi

# Get files summary
FILES_COUNT=$(python3 << 'PYTHON_SCRIPT' 2>/dev/null || echo "0"
import json

try:
    with open('.claude/capsule_persist.json', 'r') as f:
        data = json.load(f)
    print(len(data.get('key_files', [])))
except:
    print("0")
PYTHON_SCRIPT
)

if [ "$FILES_COUNT" -gt 0 ]; then
  RESTORE_CONTEXT="$RESTORE_CONTEXT | $FILES_COUNT key files"
fi

# Output valid JSON for hooks that expect it
if [ -n "$RESTORE_CONTEXT" ]; then
  python3 -c "
import json
import sys
context = sys.argv[1] if len(sys.argv) > 1 else ''
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'SessionStart',
        'additionalContext': '[SESSION RESTORE] ' + context
    }
}))
" "$RESTORE_CONTEXT" 2>/dev/null || exit 0
fi

exit 0

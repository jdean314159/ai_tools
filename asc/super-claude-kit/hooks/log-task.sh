#!/bin/bash

# Log Task - Record task status changes to session and shared hive
# Usage: log-task.sh <status> "<content>"
# Status: pending, in_progress, completed

STATUS="${1:-pending}"
CONTENT="${2:-}"

[ -z "$CONTENT" ] && exit 0

# Get session info
WORKER_PROFILE="${CLAUDE_WORKER_PROFILE:-default}"
SESSION_ID="${CLAUDE_SESSION_ID:-$WORKER_PROFILE}"
SESSION_DIR=".claude/sessions/$SESSION_ID"

mkdir -p "$SESSION_DIR" 2>/dev/null

# Create JSON data
JSON_DATA=$(python3 -c "
import json
import sys
print(json.dumps({
    'status': sys.argv[1],
    'content': sys.argv[2]
}, separators=(',', ':')))
" "$STATUS" "$CONTENT" 2>/dev/null)

[ -z "$JSON_DATA" ] && exit 0

# Log to session (local)
echo "$JSON_DATA" >> "$SESSION_DIR/tasks.log"

# Log to shared hive (team-wide)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/shared-log-append.sh" "tasks" "$JSON_DATA"

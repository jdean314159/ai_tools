#!/bin/bash

# Log File Access - Record file reads/edits/writes to session and shared hive
# Usage: log-file-access.sh <path> <action>
# action: read | edit | write

FILE_PATH="${1:-}"
ACTION="${2:-read}"

[ -z "$FILE_PATH" ] && exit 0

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
    'path': sys.argv[1],
    'action': sys.argv[2]
}, separators=(',', ':')))
" "$FILE_PATH" "$ACTION" 2>/dev/null)

[ -z "$JSON_DATA" ] && exit 0

# Log to session (local)
echo "$JSON_DATA" >> "$SESSION_DIR/file_access.log"

# Log to shared hive (team-wide)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/shared-log-append.sh" "file_access" "$JSON_DATA"

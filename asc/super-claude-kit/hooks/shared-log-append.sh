#!/bin/bash

# Shared Log Append - Thread-safe append to shared hive logs
# Uses flock for file locking to prevent corruption from parallel workers

# Usage: shared-log-append.sh <log_type> <json_data>
# log_type: file_access | discoveries | tasks
# json_data: JSON object to append (will be validated)

LOG_TYPE="${1:-}"
JSON_DATA="${2:-}"

if [ -z "$LOG_TYPE" ] || [ -z "$JSON_DATA" ]; then
  exit 0
fi

# Shared directory
SHARED_DIR=".claude/shared"
mkdir -p "$SHARED_DIR"

# Determine log file
case "$LOG_TYPE" in
  file_access) LOG_FILE="$SHARED_DIR/file_access.log" ;;
  discoveries) LOG_FILE="$SHARED_DIR/discoveries.log" ;;
  tasks) LOG_FILE="$SHARED_DIR/tasks.log" ;;
  *) exit 0 ;;
esac

# Create log file if it doesn't exist
touch "$LOG_FILE"

# Add profile and timestamp to JSON if not present
PROFILE="${CLAUDE_WORKER_PROFILE:-default}"
TIMESTAMP=$(date +%s)

# Enhance JSON with profile and timestamp using Python (safe JSON handling)
ENHANCED_JSON=$(python3 -c "
import json
import sys

try:
    data = json.loads(sys.argv[1])
    data['profile'] = sys.argv[2]
    data['timestamp'] = int(sys.argv[3])
    print(json.dumps(data, separators=(',', ':')))
except:
    pass
" "$JSON_DATA" "$PROFILE" "$TIMESTAMP" 2>/dev/null || echo "")

if [ -z "$ENHANCED_JSON" ]; then
  exit 0
fi

# Append with file locking (flock)
# Use file descriptor 200 for locking
(
  flock -x 200 2>/dev/null || true
  echo "$ENHANCED_JSON" >> "$LOG_FILE"
) 200>"$LOG_FILE.lock"

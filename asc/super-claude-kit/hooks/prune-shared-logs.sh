#!/bin/bash

# Prune Shared Logs - Remove entries older than 48 hours
# Called at session start to keep shared hive data bounded

SHARED_DIR=".claude/shared"
RETENTION_SECONDS=$((48 * 60 * 60))  # 48 hours in seconds
NOW=$(date +%s)
CUTOFF=$((NOW - RETENTION_SECONDS))

# Exit if no shared directory
[ ! -d "$SHARED_DIR" ] && exit 0

# Process each log file
for LOG_FILE in "$SHARED_DIR"/*.log; do
  [ ! -f "$LOG_FILE" ] && continue

  TEMP_FILE="${LOG_FILE}.tmp"

  # Filter lines with flock to prevent concurrent modification
  (
    flock -x 200 2>/dev/null || true

    # Keep only lines with timestamp >= cutoff
    # Each line is JSON with "timestamp" field
    python3 -c "
import sys
import json

cutoff = int(sys.argv[1])

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        data = json.loads(line)
        if data.get('timestamp', 0) >= cutoff:
            print(line)
    except:
        # Keep malformed lines (safety)
        print(line)
" "$CUTOFF" < "$LOG_FILE" > "$TEMP_FILE"

    # Replace original with filtered
    mv "$TEMP_FILE" "$LOG_FILE"

  ) 200>"$LOG_FILE.lock"
done

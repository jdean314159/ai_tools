#!/bin/bash
# Remove worker-specific temporary files to prevent collisions.
# Called at session start and session end.

# Redirect stderr to prevent display corruption
exec 2>>.claude/hook-errors.log

# Get session directory
WORKER_PROFILE="${CLAUDE_WORKER_PROFILE:-default}"
SESSION_ID="${CLAUDE_SESSION_ID:-$WORKER_PROFILE}"
SESSION_DIR=".claude/sessions/$SESSION_ID"

IDENTITY_FILE="$SESSION_DIR/current_worker_identity.json"
DEFAULT_PREFIX="worker"

# Try to get prefix from identity file
PREFIX=""
if [ -f "$IDENTITY_FILE" ]; then
    PREFIX=$(python3 -c "
import json
import sys
try:
    data = json.load(open('$IDENTITY_FILE'))
    print(data.get('temp_prefix', 'worker'))
except:
    print('worker')
" 2>/dev/null) || PREFIX="$DEFAULT_PREFIX"
fi

# Fallback to profile-based prefix if not set
if [ -z "$PREFIX" ]; then
    # Slugify the profile name
    PREFIX=$(echo "$WORKER_PROFILE" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_' | sed 's/^_//;s/_$//')
    PREFIX="${PREFIX:-worker}"
fi

# Clean up temp files matching worker patterns
# Look in current directory and session directory
for dir in "." "$SESSION_DIR"; do
    [ -d "$dir" ] || continue

    # Remove matching temp files
    rm -f "$dir"/tmp_agentmail_${PREFIX}_*.json 2>/dev/null || true
    rm -f "$dir"/tmp_worker_${PREFIX}_*.json 2>/dev/null || true
    rm -f "$dir"/tmp_${PREFIX}_*.json 2>/dev/null || true
    rm -f "$dir"/tmp_workermail_${PREFIX}_*.json 2>/dev/null || true
done

exit 0

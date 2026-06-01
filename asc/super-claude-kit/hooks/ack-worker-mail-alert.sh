#!/bin/bash
# Clear agent mail alert messages after inbox has been processed.

# Get session directory
WORKER_PROFILE="${CLAUDE_WORKER_PROFILE:-default}"
SESSION_ID="${CLAUDE_SESSION_ID:-$WORKER_PROFILE}"
SESSION_DIR=".claude/sessions/$SESSION_ID"

ALERT_FILE="$SESSION_DIR/agent_mail_alert.txt"

# Clear the alert file
> "$ALERT_FILE" 2>/dev/null || true

echo "Agent Mail alert cleared"

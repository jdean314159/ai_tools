#!/bin/bash
# UserPromptSubmit Hook - Super Claude Kit (Optimized for speed)
# CRITICAL: This hook must complete in <100ms to avoid UI slowdown
#
# Only essential checks, no external scripts, minimal Python

# Redirect stderr to log file - CRITICAL for preventing display corruption
exec 2>>.claude/hook-errors.log

# Quick exit if quiet mode
[ "${CLAUDE_QUIET_HOOKS:-false}" = "true" ] && exit 0

# Read JSON input - use 'read' builtin for speed
INPUT_JSON=""
read -t 1 -r INPUT_JSON || INPUT_JSON="{}"

# Quick bail if empty input
[ -z "$INPUT_JSON" ] || [ "$INPUT_JSON" = "{}" ] && exit 0

# Session directory setup (use env var if available)
SESSION_DIR="${CLAUDE_SESSION_DIR:-.claude/sessions/default}"

# Only check for Agent Mail alerts - this is the most important feature
ALERT_FILE="$SESSION_DIR/agent_mail_alert.txt"
if [ -f "$ALERT_FILE" ] && [ -s "$ALERT_FILE" ]; then
  ALERT_CONTENT=$(cat "$ALERT_FILE" 2>/dev/null)
  # Output JSON with alert context
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":\"[AGENT MAIL ALERT] You have unread messages. Process inbox and run: ./.claude/hooks/ack-worker-mail-alert.sh\"}}"
  exit 0
fi

# Silent exit - no context to add
exit 0

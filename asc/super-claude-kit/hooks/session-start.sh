#!/bin/bash

# Super Claude Kit Session Start Hook (Pure Bash - WSL Compatible)
# Injects full worker configuration into Claude's context
# With hive integration: prunes old logs, injects team discoveries/tasks

# Get worker profile
WORKER_PROFILE="${CLAUDE_WORKER_PROFILE:-default}"
SESSION_ID="${CLAUDE_SESSION_ID:-$WORKER_PROFILE}"
SESSION_DIR=".claude/sessions/$SESSION_ID"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create session directories
mkdir -p "$SESSION_DIR" 2>/dev/null
mkdir -p ".claude/shared" 2>/dev/null
date +%s > "$SESSION_DIR/session_start.txt"
[ ! -f "$SESSION_DIR/message_count.txt" ] && echo "0" > "$SESSION_DIR/message_count.txt"

# Prune old shared logs (48-hour retention)
bash "$SCRIPT_DIR/prune-shared-logs.sh" 2>/dev/null &

# Clean up old temp files from previous sessions
rm -f "$SESSION_DIR"/tmp_workermail_*.json 2>/dev/null

# Load worker file
WORKER_FILE=".claude/workers/${WORKER_PROFILE}.md"
WORKER_CONTENT=""

if [ -f "$WORKER_FILE" ]; then
  WORKER_CONTENT=$(cat "$WORKER_FILE")
fi

# Parse identity from frontmatter (fast)
MAILBOX=$(echo "$WORKER_CONTENT" | grep -m1 "mailbox:" | sed 's/.*mailbox:[[:space:]]*//' | tr -d '"' | tr -d "'" | tr -d ' ')
TEMP_PREFIX=$(echo "$WORKER_CONTENT" | grep -m1 "temp_prefix:" | sed 's/.*temp_prefix:[[:space:]]*//' | tr -d '"' | tr -d "'" | tr -d ' ')
PREFERRED_NAME=$(echo "$WORKER_CONTENT" | grep -m1 "preferred_name:" | sed 's/.*preferred_name:[[:space:]]*//' | tr -d '"' | tr -d "'" | tr -d ' ')
USES_BEADS=$(echo "$WORKER_CONTENT" | grep -m1 "uses_beads:" | sed 's/.*uses_beads:[[:space:]]*//' | tr -d '"' | tr -d "'" | tr -d ' ')

# Defaults
[ -z "$MAILBOX" ] && MAILBOX="${WORKER_PROFILE//-/}"
[ -z "$TEMP_PREFIX" ] && TEMP_PREFIX="${WORKER_PROFILE//-/_}"
[ -z "$PREFERRED_NAME" ] && PREFERRED_NAME="$MAILBOX"

# Mark context as injected
date +%s > "$SESSION_DIR/context_injected.marker"

# Get initial capsule (team discoveries, tasks, files)
CAPSULE_CONTEXT=""
if [ -f "$SCRIPT_DIR/inject-capsule.sh" ]; then
  CAPSULE_CONTEXT=$(bash "$SCRIPT_DIR/inject-capsule.sh" 2>/dev/null)
fi

# Bootstrap Beads if enabled
BEADS_READY=""
if [ "$USES_BEADS" = "true" ] && command -v bd &>/dev/null; then
  mkdir -p ".claude/beads" 2>/dev/null
  bd quickstart >> ".claude/beads/quickstart.log" 2>&1
  BEADS_READY=$(bd ready --json 2>/dev/null | head -20)
  if [ -n "$BEADS_READY" ]; then
    BEADS_READY="
<beads-ready-queue>
$BEADS_READY
</beads-ready-queue>"
  fi
fi

# Build full context with worker instructions
CONTEXT="[WORKER ROLE: $WORKER_PROFILE]

*** AGENT MAIL IDENTITY ***
Your Mailbox: $MAILBOX
Preferred Name: $PREFERRED_NAME
Use \"$MAILBOX\" as agent_name in all Agent Mail operations.
*** END AGENT MAIL IDENTITY ***

Session: $SESSION_ID
Session Dir: $SESSION_DIR
Temp file pattern: tmp_workermail_${TEMP_PREFIX}_<purpose>.json

---

$WORKER_CONTENT

---
$BEADS_READY
$CAPSULE_CONTEXT

GUIDELINES:
- Log discoveries: ./.claude/hooks/log-discovery.sh <category> \"<description>\"
- Categories: pattern, insight, decision, architecture, bug, optimization, achievement
- Check <team-discoveries> before duplicating work
- Log file access: ./.claude/hooks/log-file-access.sh \"<path>\" \"read|edit|write\"
- Log tasks: ./.claude/hooks/log-task.sh \"<status>\" \"<content>\""

# Output JSON using Python for proper escaping (required for large content with special chars)
python3 -c "
import json
import sys

context = sys.stdin.read()
msg = 'Super Claude Kit - Worker $WORKER_PROFILE loaded'

print(json.dumps({
    'systemMessage': msg,
    'hookSpecificOutput': {
        'hookEventName': 'SessionStart',
        'additionalContext': context
    }
}))
" <<< "$CONTEXT"

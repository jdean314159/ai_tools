#!/bin/bash
# Initialize capsule session tracking
# Called from SessionStart hook

set -euo pipefail
source ".claude/lib/session-env.sh"

SESSION_START_FILE="$(session_path 'session_start.txt')"
MESSAGE_COUNT_FILE="$(session_path 'message_count.txt')"
FILE_LOG="$(session_path 'session_files.log')"
TASK_FILE="$(session_path 'current_tasks.log')"
SUBAGENT_LOG="$(session_path 'subagent_results.log')"
DISCOVERY_LOG="$(session_path 'session_discoveries.log')"
SNAPSHOT_FILE="$(session_path 'last_snapshot.txt')"

# Create required directories (shared is never cleared)
mkdir -p .claude
mkdir -p .claude/shared
mkdir -p .claude/workers
mkdir -p "$CLAUDE_SESSION_DIR"

# Set session start time
date +%s > "$SESSION_START_FILE"

# Reset message count
echo "0" > "$MESSAGE_COUNT_FILE"

# Clear file log (start fresh each session)
> "$FILE_LOG"

# Clear task log (start fresh each session)
> "$TASK_FILE"

# Clear sub-agent log (start fresh each session)
> "$SUBAGENT_LOG"

# Clear discovery log (start fresh each session)
> "$DISCOVERY_LOG"

# Initialize git snapshot for change detection (if git available)
if git rev-parse --git-dir > /dev/null 2>&1; then
  git status --porcelain 2>/dev/null > "$SNAPSHOT_FILE" || touch "$SNAPSHOT_FILE"
else
  # No git - create empty snapshot (mtime-based detection will be used)
  touch "$SNAPSHOT_FILE"
fi

echo "✓ Capsule session initialized" >&2

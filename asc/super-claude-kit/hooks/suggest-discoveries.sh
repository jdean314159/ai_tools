#!/bin/bash
# Discovery Suggestion Engine
# Analyzes recent activity and suggests potential discoveries to log
#
# IMPORTANT: This hook must NOT output to stdout - it corrupts Claude Code UI.
# For PostToolUse/PreToolUse hooks, only valid JSON or nothing should be output.
# Discovery suggestions are logged to a session file for optional review.

# Redirect stderr to log file
exec 2>>.claude/hook-errors.log

# Source session environment helpers (with error handling)
if [ -f ".claude/lib/session-env.sh" ]; then
  source ".claude/lib/session-env.sh" 2>/dev/null || true
fi

# Get session directory
SESSION_DIR="${CLAUDE_SESSION_DIR:-.claude/sessions/default}"
mkdir -p "$SESSION_DIR" 2>/dev/null || true

FILE_LOG="$SESSION_DIR/session_files.log"
TASK_LOG="$SESSION_DIR/current_tasks.log"
SUBAGENT_LOG="$SESSION_DIR/subagent_results.log"
SUGGESTIONS_LOG="$SESSION_DIR/discovery_suggestions.log"
SUGGESTIONS_SHOWN_LOG="$SESSION_DIR/suggestions_shown.log"

# Only run analysis periodically (not on every tool use)
LAST_RUN_FILE="$SESSION_DIR/last_discovery_check.txt"
CURRENT_TIME=$(date +%s 2>/dev/null || echo "0")
if [ -f "$LAST_RUN_FILE" ]; then
  LAST_RUN=$(cat "$LAST_RUN_FILE" 2>/dev/null || echo "0")
  # Only run every 5 minutes
  if [ $((CURRENT_TIME - LAST_RUN)) -lt 300 ]; then
    exit 0
  fi
fi
echo "$CURRENT_TIME" > "$LAST_RUN_FILE" 2>/dev/null || true

SUGGESTION_COUNT=0
SUGGESTIONS=""

# Analyze git changes for patterns
if git status --porcelain 2>/dev/null | grep -q "^M.*\.sh$"; then
  SUGGESTIONS="${SUGGESTIONS}[pattern] Shell scripts modified - consider documenting script patterns\n"
  SUGGESTION_COUNT=$((SUGGESTION_COUNT + 1))
fi

if git status --porcelain 2>/dev/null | grep -q "^M.*\.ts$"; then
  SUGGESTIONS="${SUGGESTIONS}[pattern] TypeScript files modified - consider documenting code patterns\n"
  SUGGESTION_COUNT=$((SUGGESTION_COUNT + 1))
fi

# Analyze file access patterns
if [ -f "$FILE_LOG" ]; then
  MOST_EDITED=$(awk -F',' '$2=="edit" {print $1}' "$FILE_LOG" 2>/dev/null | sort | uniq -c | sort -rn | head -1 | awk '{print $2}')
  if [ -n "$MOST_EDITED" ]; then
    SUGGESTIONS="${SUGGESTIONS}[insight] Deep work on $MOST_EDITED - document key learnings\n"
    SUGGESTION_COUNT=$((SUGGESTION_COUNT + 1))
  fi

  NEW_FILES=$(grep -c ",write," "$FILE_LOG" 2>/dev/null || echo "0")
  if [ "$NEW_FILES" -gt 3 ]; then
    SUGGESTIONS="${SUGGESTIONS}[architecture] Created $NEW_FILES new files - document decisions\n"
    SUGGESTION_COUNT=$((SUGGESTION_COUNT + 1))
  fi
fi

# Analyze task completion
if [ -f "$TASK_LOG" ]; then
  COMPLETED_TASKS=$(grep -c "^completed|" "$TASK_LOG" 2>/dev/null || echo "0")
  if [ "$COMPLETED_TASKS" -gt 3 ]; then
    SUGGESTIONS="${SUGGESTIONS}[optimization] Completed $COMPLETED_TASKS tasks - document process improvements\n"
    SUGGESTION_COUNT=$((SUGGESTION_COUNT + 1))
  fi
fi

# Log suggestions to file (not stdout) for optional review
if [ $SUGGESTION_COUNT -gt 0 ]; then
  {
    echo "=== Discovery Suggestions ($(date -Iseconds 2>/dev/null || date)) ==="
    echo -e "$SUGGESTIONS"
    echo "Use: ./.claude/hooks/log-discovery.sh \"<category>\" \"<content>\""
    echo ""
  } >> "$SUGGESTIONS_LOG" 2>/dev/null || true
fi

# Silent exit - no stdout output to avoid UI corruption
exit 0

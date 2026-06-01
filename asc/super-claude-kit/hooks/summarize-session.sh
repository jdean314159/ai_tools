#!/bin/bash
# Intelligent Session Summarization
# Generates TL;DR of current session
#
# IMPORTANT: This script outputs to a log file, NOT stdout, to avoid
# corrupting Claude Code UI. Session summaries are saved for optional review.

# Redirect stderr to log file
exec 2>>.claude/hook-errors.log

# Source session environment helpers
if [ -f ".claude/lib/session-env.sh" ]; then
  source ".claude/lib/session-env.sh" 2>/dev/null || true
fi

# Session directory
SESSION_DIR="${CLAUDE_SESSION_DIR:-.claude/sessions/default}"
mkdir -p "$SESSION_DIR" 2>/dev/null || true

SESSION_START_FILE="$SESSION_DIR/session_start.txt"
MESSAGE_COUNT_FILE="$SESSION_DIR/message_count.txt"
TASK_LOG="$SESSION_DIR/current_tasks.log"
FILE_LOG="$SESSION_DIR/session_files.log"
DISCOVERY_LOG="$SESSION_DIR/session_discoveries.log"
SUBAGENT_LOG="$SESSION_DIR/subagent_results.log"
SUMMARY_LOG="$SESSION_DIR/session_summary.log"

SESSION_START=$(cat "$SESSION_START_FILE" 2>/dev/null || date +%s)
CURRENT_TIME=$(date +%s)
DURATION=$((CURRENT_TIME - SESSION_START))
MESSAGE_COUNT=$(cat "$MESSAGE_COUNT_FILE" 2>/dev/null || echo "0")

# Convert duration to human readable
if [ $DURATION -lt 60 ]; then
  DUR_STR="${DURATION}s"
elif [ $DURATION -lt 3600 ]; then
  DUR_STR="$((DURATION / 60))m"
else
  DUR_STR="$((DURATION / 3600))h $((DURATION % 3600 / 60))m"
fi

# Write summary to log file instead of stdout (prevents UI corruption)
{
  echo ""
  echo "=== SESSION SUMMARY ($(date -Iseconds 2>/dev/null || date)) ==="
  echo ""
  echo "Duration: $DUR_STR | Messages: $MESSAGE_COUNT"
  echo "Branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"
  echo ""

  # Tasks summary
  if [ -f "$TASK_LOG" ] && [ -s "$TASK_LOG" ]; then
    COMPLETED_COUNT=$(grep -c "^completed|" "$TASK_LOG" 2>/dev/null || echo "0")
    IN_PROGRESS_COUNT=$(grep -c "^in_progress|" "$TASK_LOG" 2>/dev/null || echo "0")
    PENDING_COUNT=$(grep -c "^pending|" "$TASK_LOG" 2>/dev/null || echo "0")

    echo "Tasks: Completed=$COMPLETED_COUNT | InProgress=$IN_PROGRESS_COUNT | Pending=$PENDING_COUNT"

    if [ "$COMPLETED_COUNT" -gt 0 ]; then
      echo "Completed:"
      grep "^completed|" "$TASK_LOG" 2>/dev/null | cut -d'|' -f2 | head -5 | while read -r task; do
        echo "  - $task"
      done
    fi
    echo ""
  fi

  # Files worked on
  if [ -f "$FILE_LOG" ] && [ -s "$FILE_LOG" ]; then
    TOTAL_FILES=$(awk -F',' '{print $1}' "$FILE_LOG" 2>/dev/null | sort -u | wc -l | tr -d ' ')
    EDITED_FILES=$(grep ",edit," "$FILE_LOG" 2>/dev/null | wc -l | tr -d ' ')
    WRITTEN_FILES=$(grep ",write," "$FILE_LOG" 2>/dev/null | wc -l | tr -d ' ')

    echo "Files: $TOTAL_FILES unique (edited=$EDITED_FILES, created=$WRITTEN_FILES)"
    echo ""
  fi

  # Key discoveries
  if [ -f "$DISCOVERY_LOG" ] && [ -s "$DISCOVERY_LOG" ]; then
    DISCOVERY_COUNT=$(wc -l < "$DISCOVERY_LOG" 2>/dev/null | tr -d ' ')
    echo "Discoveries: $DISCOVERY_COUNT insights"
    echo ""
  fi

  # Sub-agent usage
  if [ -f "$SUBAGENT_LOG" ] && [ -s "$SUBAGENT_LOG" ]; then
    SUBAGENT_COUNT=$(wc -l < "$SUBAGENT_LOG" 2>/dev/null | tr -d ' ')
    echo "Sub-Agents: $SUBAGENT_COUNT used"
    echo ""
  fi

  # Git changes
  DIRTY_COUNT=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  if [ "$DIRTY_COUNT" -gt 0 ]; then
    echo "Uncommitted: $DIRTY_COUNT dirty files"
    echo ""
  fi

  echo "=== END SESSION SUMMARY ==="
  echo ""
} >> "$SUMMARY_LOG" 2>/dev/null

# Silent exit - no stdout output to avoid UI corruption
exit 0

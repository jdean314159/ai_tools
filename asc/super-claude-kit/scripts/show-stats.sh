#!/bin/bash
# Super Claude Kit Stats Dashboard
# Shows usage statistics for the current session

set -euo pipefail
source ".claude/lib/session-env.sh"

FILES_LOG="$(session_path 'session_files.log')"
DISC_LOG="$(session_path 'session_discoveries.log')"
TASK_LOG="$(session_path 'current_tasks.log')"
SUBAGENT_LOG="$(session_path 'subagent_results.log')"
MESSAGE_COUNT_FILE="$(session_path 'message_count.txt')"
SESSION_START_FILE="$(session_path 'session_start.txt')"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Super Claude Kit Usage Statistics"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if .claude directory exists
if [ ! -d ".claude" ]; then
  echo "⚠️  Super Claude Kit not initialized in this directory"
  exit 0
fi

# Get counts
FILES_COUNT=0
DISC_COUNT=0
TASKS_COUNT=0
SUBAGENT_COUNT=0
MESSAGE_COUNT=0

[ -f "$FILES_LOG" ] && FILES_COUNT=$(wc -l < "$FILES_LOG" 2>/dev/null || echo 0)
[ -f "$DISC_LOG" ] && DISC_COUNT=$(wc -l < "$DISC_LOG" 2>/dev/null || echo 0)
[ -f "$TASK_LOG" ] && TASKS_COUNT=$(wc -l < "$TASK_LOG" 2>/dev/null || echo 0)
[ -f "$SUBAGENT_LOG" ] && SUBAGENT_COUNT=$(wc -l < "$SUBAGENT_LOG" 2>/dev/null || echo 0)
[ -f "$MESSAGE_COUNT_FILE" ] && MESSAGE_COUNT=$(cat "$MESSAGE_COUNT_FILE" 2>/dev/null || echo 0)

echo "📁 Files accessed: $FILES_COUNT"
echo "💡 Discoveries logged: $DISC_COUNT"
echo "✅ Tasks tracked: $TASKS_COUNT"
echo "🤖 Sub-agents used: $SUBAGENT_COUNT"
echo "💬 Messages in session: $MESSAGE_COUNT"
echo ""

# Show last entries if they exist
if [ -f "$FILES_LOG" ] && [ "$FILES_COUNT" -gt 0 ]; then
  echo "📄 Last file accessed:"
  tail -1 "$FILES_LOG" | awk -F'|' '{print "   " $1 " (" $2 ")"}'
  echo ""
fi

if [ -f "$DISC_LOG" ] && [ "$DISC_COUNT" -gt 0 ]; then
  echo "💡 Last discovery:"
  tail -1 "$DISC_LOG" | awk -F'|' '{print "   [" $1 "] " $2}'
  echo ""
fi

if [ -f "$TASK_LOG" ] && [ "$TASKS_COUNT" -gt 0 ]; then
  echo "✅ Current task:"
  tail -1 "$TASK_LOG" | awk -F'|' '{print "   [" $1 "] " $2}'
  echo ""
fi

# Session duration
if [ -f "$SESSION_START_FILE" ]; then
  session_start=$(cat "$SESSION_START_FILE")
  current_time=$(date +%s)
  duration=$((current_time - session_start))
  minutes=$((duration / 60))
  echo "⏱️  Session duration: ${minutes}m"
  echo ""
fi

# Capsule health check
if [ "$MESSAGE_COUNT" -gt 0 ]; then
  total_logs=$((FILES_COUNT + DISC_COUNT + TASKS_COUNT))
  logs_per_message=$(echo "scale=1; $total_logs / $MESSAGE_COUNT" | bc 2>/dev/null || echo "0")

  echo "🏥 Capsule Health:"
  if (( $(echo "$logs_per_message >= 1.0" | bc -l 2>/dev/null || echo 0) )); then
    echo "   ✅ Active ($logs_per_message logs/message)"
  elif (( $(echo "$logs_per_message >= 0.5" | bc -l 2>/dev/null || echo 0) )); then
    echo "   ⚠️  Moderate ($logs_per_message logs/message)"
  else
    echo "   ❌ Low ($logs_per_message logs/message)"
  fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

#!/bin/bash
# Session End Hook - Minimal version
# Runs when Claude Code session ends
# MUST NOT output anything that breaks display

# Redirect stderr to prevent display corruption
exec 2>>.claude/hook-errors.log

# Create session directory if it doesn't exist
WORKER_PROFILE="${CLAUDE_WORKER_PROFILE:-default}"
SESSION_ID="${CLAUDE_SESSION_ID:-$WORKER_PROFILE}"
SESSION_DIR=".claude/sessions/$SESSION_ID"
mkdir -p "$SESSION_DIR" 2>/dev/null || true

# Persist capsule if script exists
[ -x ".claude/hooks/persist-capsule.sh" ] && ./.claude/hooks/persist-capsule.sh 2>/dev/null || true

# Prune old shared logs
[ -x ".claude/hooks/prune-shared-logs.sh" ] && ./.claude/hooks/prune-shared-logs.sh 2>/dev/null || true

# Clean up worker temp files
[ -x ".claude/hooks/cleanup-worker-temp.sh" ] && ./.claude/hooks/cleanup-worker-temp.sh 2>/dev/null || true

# Clean up session tracking files
rm -f "$SESSION_DIR/recent_reads.log" 2>/dev/null || true
rm -f "$SESSION_DIR/read_warnings_shown.log" 2>/dev/null || true
rm -f "$SESSION_DIR/suggestions_shown.log" 2>/dev/null || true
rm -f "$SESSION_DIR/quality_suggestions_shown.log" 2>/dev/null || true
rm -f "$SESSION_DIR/quality_check_state.txt" 2>/dev/null || true
rm -f "$SESSION_DIR/capsule.hash" 2>/dev/null || true

exit 0

#!/bin/bash
# Load Recent Discoveries from Exploration Journal
# Displays recent journal entries relevant to current work

# Redirect stderr to prevent display issues
exec 2>>.claude/hook-errors.log

JOURNAL_DIR="docs/exploration"
CURRENT_SESSION="$JOURNAL_DIR/CURRENT_SESSION.md"

# Check if journal exists
if [ ! -f "$CURRENT_SESSION" ]; then
  exit 0  # No journal to load
fi

# Cross-platform file modification time
get_mtime() {
  local file="$1"
  stat -c %Y "$file" 2>/dev/null && return
  stat -f %m "$file" 2>/dev/null && return
  python3 -c "import os; print(int(os.path.getmtime('$file')))" 2>/dev/null && return
  echo "0"
}

# Check if journal was updated recently (last 7 days)
if [ -f "$CURRENT_SESSION" ]; then
  LAST_MODIFIED=$(get_mtime "$CURRENT_SESSION")
  CURRENT_TIME=$(date +%s 2>/dev/null || python3 -c "import time; print(int(time.time()))" 2>/dev/null || echo "0")
  DAYS_SINCE=$(( (CURRENT_TIME - LAST_MODIFIED) / 86400 ))

  if [ $DAYS_SINCE -gt 7 ]; then
    exit 0  # Journal too old
  fi

  # Display journal excerpt
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "📚 EXPLORATION JOURNAL (Updated $DAYS_SINCE day(s) ago)"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo "Recent discoveries from journal:"
  echo ""

  # Show last 10 discovery lines
  grep -E "^- (🔍|💭|🎯|🏗️|🐛|⚡)" "$CURRENT_SESSION" 2>/dev/null | tail -n 10 || echo "   (No recent discoveries)"

  echo ""
  echo "💡 Full journal: $CURRENT_SESSION"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
fi

#!/bin/bash

# Log Discovery - Record insights/patterns to session and shared hive
# Usage: log-discovery.sh <category> "<description>"
# Categories: pattern, insight, decision, architecture, bug, optimization, achievement

CATEGORY="${1:-insight}"
DESCRIPTION="${2:-}"

[ -z "$DESCRIPTION" ] && exit 0

# Get session info
WORKER_PROFILE="${CLAUDE_WORKER_PROFILE:-default}"
SESSION_ID="${CLAUDE_SESSION_ID:-$WORKER_PROFILE}"
SESSION_DIR=".claude/sessions/$SESSION_ID"

mkdir -p "$SESSION_DIR" 2>/dev/null

# Create JSON data
JSON_DATA=$(python3 -c "
import json
import sys
print(json.dumps({
    'category': sys.argv[1],
    'description': sys.argv[2]
}, separators=(',', ':')))
" "$CATEGORY" "$DESCRIPTION" 2>/dev/null)

[ -z "$JSON_DATA" ] && exit 0

# Log to session (local)
echo "$JSON_DATA" >> "$SESSION_DIR/discoveries.log"

# Log to shared hive (team-wide)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/shared-log-append.sh" "discoveries" "$JSON_DATA"

# Auto-create Beads issue for bugs if uses_beads is enabled
if [ "$CATEGORY" = "bug" ]; then
  WORKER_FILE=".claude/workers/${WORKER_PROFILE}.md"
  if [ -f "$WORKER_FILE" ] && grep -q "uses_beads:.*true" "$WORKER_FILE" 2>/dev/null; then
    # Create bug issue in Beads
    mkdir -p ".claude/beads" 2>/dev/null
    if command -v bd &>/dev/null; then
      ISSUE_RESULT=$(bd create --type bug --priority 1 --labels "bug,auto" --title "$DESCRIPTION" 2>&1)
      echo "[$(date -Iseconds)] Bug logged: $DESCRIPTION -> $ISSUE_RESULT" >> ".claude/beads/bug-issues.log"
    fi
  fi
fi

#!/bin/bash
# Cross-Session Capsule Persistence
# Saves key session state for next session to restore

set -euo pipefail
source ".claude/lib/session-env.sh"

# First, show session summary
./.claude/hooks/summarize-session.sh 2>/dev/null

PERSIST_FILE=".claude/capsule_persist.json"
TIMESTAMP=$(date +%s)
SESSION_START_FILE="$(session_path 'session_start.txt')"
SESSION_START=$(cat "$SESSION_START_FILE" 2>/dev/null || echo "$TIMESTAMP")
SESSION_DURATION=$((TIMESTAMP - SESSION_START))

# Get git info if available
if git rev-parse --git-dir > /dev/null 2>&1; then
  GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "none")
  GIT_HEAD=$(git rev-parse --short HEAD 2>/dev/null || echo "none")
else
  GIT_BRANCH="none"
  GIT_HEAD="none"
fi

# Create persistence object
cat > "$PERSIST_FILE" << EOF
{
  "last_session": {
    "ended_at": $TIMESTAMP,
    "duration_seconds": $SESSION_DURATION,
    "branch": "$GIT_BRANCH",
    "head": "$GIT_HEAD"
  },
  "discoveries": [
EOF

# Add last 10 discoveries
SESSION_DISCOVERY_LOG="$(session_path 'session_discoveries.log')"
if [ -f "$SESSION_DISCOVERY_LOG" ]; then
  tail -n 10 "$SESSION_DISCOVERY_LOG" 2>/dev/null | while IFS=',' read -r ts category content; do
    # Escape content for JSON
    SAFE_CONTENT=$(echo "$content" | sed 's/"/\\"/g' | sed "s/'/\\'/g")
    echo "    {\"timestamp\": $ts, \"category\": \"$category\", \"content\": \"$SAFE_CONTENT\"}," >> "$PERSIST_FILE"
  done

  # Remove trailing comma from last item
  sed -i.bak '$ s/,$//' "$PERSIST_FILE" 2>/dev/null || sed -i '$ s/,$//' "$PERSIST_FILE" 2>/dev/null
  rm -f "$PERSIST_FILE.bak" 2>/dev/null || true
fi

cat >> "$PERSIST_FILE" << EOF
  ],
  "key_files": [
EOF

# Add last 15 accessed files
SESSION_FILE_LOG="$(session_path 'session_files.log')"
if [ -f "$SESSION_FILE_LOG" ]; then
  tail -n 15 "$SESSION_FILE_LOG" 2>/dev/null | awk -F',' '{print $1}' | sort -u | while read -r file; do
    echo "    \"$file\"," >> "$PERSIST_FILE"
  done

  # Remove trailing comma
  sed -i.bak '$ s/,$//' "$PERSIST_FILE" 2>/dev/null || sed -i '$ s/,$//' "$PERSIST_FILE" 2>/dev/null
  rm -f "$PERSIST_FILE.bak" 2>/dev/null || true
fi

cat >> "$PERSIST_FILE" << EOF
  ],
  "sub_agents": [
EOF

# Add last 5 sub-agent results
SUBAGENT_LOG="$(session_path 'subagent_results.log')"
if [ -f "$SUBAGENT_LOG" ]; then
  tail -n 5 "$SUBAGENT_LOG" 2>/duv? need fix-- use actual patch.
    SAFE_SUMMARY=$(echo "$summary" | sed 's/"/\\"/g' | sed "s/'/\\'/g")
    echo "    {\"timestamp\": $ts, \"type\": \"$type\", \"summary\": \"$SAFE_SUMMARY\"}," >> "$PERSIST_FILE"
  done

  # Remove trailing comma
  sed -i.bak '$ s/,$//' "$PERSIST_FILE" 2>/dev/null || sed -i '$ s/,$//' "$PERSIST_FILE" 2>/dev/null
  rm -f "$PERSIST_FILE.bak" 2>/dev/null || true
fi

cat >> "$PERSIST_FILE" << EOF
  ]
}
EOF

# Also sync discoveries to exploration journal
./.claude/hooks/sync-to-journal.sh 2>/dev/null

echo "✓ Session state persisted for next session" >&2

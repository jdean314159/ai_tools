#!/bin/bash
# Smart Refresh Heuristics
# Determines if capsule needs updating based on state changes
# Returns: 0 if refresh needed, 1 if can skip

# Redirect stderr to prevent display issues
exec 2>>.claude/hook-errors.log

# Source session environment with fallback
if [ -f ".claude/lib/session-env.sh" ]; then
  source ".claude/lib/session-env.sh" 2>/dev/null || true
fi

# Fallback session path function if sourcing failed
if ! command -v session_path >/dev/null 2>&1; then
  CLAUDE_SESSION_ID="${CLAUDE_SESSION_ID:-${CLAUDE_WORKER_PROFILE:-default}}"
  CLAUDE_SESSION_DIR=".claude/sessions/$CLAUDE_SESSION_ID"
  mkdir -p "$CLAUDE_SESSION_DIR" 2>/dev/null || true
  session_path() { echo "$CLAUDE_SESSION_DIR/$1"; }
fi

REFRESH_STATE_FILE="$(session_path 'last_refresh_state.txt')"
TIMESTAMP=$(date +%s 2>/dev/null || python3 -c "import time; print(int(time.time()))" 2>/dev/null || echo "0")

# Cross-platform hash function
get_hash() {
  local input="$1"
  echo "$input" | md5sum 2>/dev/null | cut -d' ' -f1 && return
  echo "$input" | md5 -q 2>/dev/null && return
  python3 -c "import hashlib,sys; print(hashlib.md5(sys.stdin.read().encode()).hexdigest())" 2>/dev/null <<< "$input" && return
  echo "unknown"
}

# Helper: Calculate hash of current state
calculate_state_hash() {
  local state_string=""

  # Git state (if available)
  if git rev-parse --git-dir > /dev/null 2>&1; then
    state_string+=$(git status --porcelain 2>/dev/null | head -20 || echo "")
  fi

  # File log size (number of lines)
  local file_log="$(session_path 'session_files.log')"
  if [ -f "$file_log" ]; then
    state_string+=$(wc -l < "$file_log" 2>/dev/null | tr -d ' ' || echo "0")
  fi

  # Task log size
  local task_log="$(session_path 'current_tasks.log')"
  if [ -f "$task_log" ]; then
    state_string+=$(wc -l < "$task_log" 2>/dev/null | tr -d ' ' || echo "0")
  fi

  # Sub-agent log size
  local agent_log="$(session_path 'subagent_results.log')"
  if [ -f "$agent_log" ]; then
    state_string+=$(wc -l < "$agent_log" 2>/dev/null | tr -d ' ' || echo "0")
  fi

  # Discovery log size
  local discovery_log="$(session_path 'session_discoveries.log')"
  if [ -f "$discovery_log" ]; then
    state_string+=$(wc -l < "$discovery_log" 2>/dev/null | tr -d ' ' || echo "0")
  fi

  # Return hash of combined state
  get_hash "$state_string"
}

# Get current state hash
CURRENT_HASH=$(calculate_state_hash)

# Check if we have previous state
if [ -f "$REFRESH_STATE_FILE" ]; then
  # Read previous state
  LAST_HASH=$(cut -d',' -f1 "$REFRESH_STATE_FILE" 2>/dev/null || echo "")
  LAST_REFRESH=$(cut -d',' -f2 "$REFRESH_STATE_FILE" 2>/dev/null || echo "0")
  TIME_SINCE_REFRESH=$((TIMESTAMP - LAST_REFRESH))

  # Compare hashes
  if [ "$CURRENT_HASH" = "$LAST_HASH" ]; then
    # State unchanged - check if too much time passed
    if [ $TIME_SINCE_REFRESH -lt 300 ]; then
      # Less than 5 minutes - safe to skip
      exit 1  # Skip refresh
    else
      # Over 5 minutes - force refresh for freshness
      echo "$CURRENT_HASH,$TIMESTAMP" > "$REFRESH_STATE_FILE"
      exit 0  # Need refresh
    fi
  else
    # State changed - need refresh
    echo "$CURRENT_HASH,$TIMESTAMP" > "$REFRESH_STATE_FILE"
    exit 0  # Need refresh
  fi
else
  # First run - need refresh
  echo "$CURRENT_HASH,$TIMESTAMP" > "$REFRESH_STATE_FILE"
  exit 0  # Need refresh
fi

#!/bin/bash

# Post-Tool-Use Hook (Pure Bash - WSL Compatible)
# Runs AFTER each tool call - auto-logs to session and shared hive
# - Auto-log Read/Edit/Write to file_access
# - Auto-log Task subagent results
# - Sync TodoWrite to tasks log

# Read input from stdin
INPUT=$(cat)

# Get session info
WORKER_PROFILE="${CLAUDE_WORKER_PROFILE:-default}"
SESSION_ID="${CLAUDE_SESSION_ID:-$WORKER_PROFILE}"
SESSION_DIR=".claude/sessions/$SESSION_ID"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$SESSION_DIR" 2>/dev/null

# Parse tool info using Python
TOOL_DATA=$(echo "$INPUT" | python3 -c "
import sys
import json

try:
    data = json.load(sys.stdin)
    tool_name = data.get('tool_name', '')
    tool_input = data.get('tool_input', {})
    tool_output = data.get('tool_output', '')

    # Extract relevant fields
    file_path = tool_input.get('file_path', tool_input.get('path', ''))
    subagent = tool_input.get('subagent_type', '')
    prompt = tool_input.get('prompt', '')[:200]  # Truncate
    todos = tool_input.get('todos', [])

    # Output as pipe-delimited
    print(f'{tool_name}|{file_path}|{subagent}|{prompt}|{json.dumps(todos)}')
except:
    print('||||[]')
" 2>/dev/null || echo "||||[]")

TOOL_NAME=$(echo "$TOOL_DATA" | cut -d'|' -f1)
FILE_PATH=$(echo "$TOOL_DATA" | cut -d'|' -f2)
SUBAGENT=$(echo "$TOOL_DATA" | cut -d'|' -f3)
PROMPT=$(echo "$TOOL_DATA" | cut -d'|' -f4)
TODOS=$(echo "$TOOL_DATA" | cut -d'|' -f5)

# === AUTO-LOG FILE ACCESS ===
if [ "$TOOL_NAME" = "Read" ] && [ -n "$FILE_PATH" ]; then
  bash "$SCRIPT_DIR/log-file-access.sh" "$FILE_PATH" "read" 2>/dev/null &
fi

if [ "$TOOL_NAME" = "Edit" ] && [ -n "$FILE_PATH" ]; then
  bash "$SCRIPT_DIR/log-file-access.sh" "$FILE_PATH" "edit" 2>/dev/null &
fi

if [ "$TOOL_NAME" = "Write" ] && [ -n "$FILE_PATH" ]; then
  bash "$SCRIPT_DIR/log-file-access.sh" "$FILE_PATH" "write" 2>/dev/null &
fi

# === AUTO-LOG SUBAGENT RESULTS ===
if [ "$TOOL_NAME" = "Task" ] && [ -n "$SUBAGENT" ]; then
  LOG_FILE="$SESSION_DIR/subagents.log"
  python3 -c "
import json
import sys
from datetime import datetime

entry = {
    'timestamp': int(datetime.now().timestamp()),
    'subagent': sys.argv[1],
    'prompt': sys.argv[2][:200]
}
print(json.dumps(entry, separators=(',', ':')))
" "$SUBAGENT" "$PROMPT" >> "$LOG_FILE" 2>/dev/null &
fi

# === SYNC TODOWRITE TO TASKS LOG ===
if [ "$TOOL_NAME" = "TodoWrite" ] && [ "$TODOS" != "[]" ]; then
  echo "$TODOS" | python3 -c "
import sys
import json
import subprocess

try:
    todos = json.load(sys.stdin)
    script_dir = sys.argv[1]

    for todo in todos:
        status = todo.get('status', 'pending')
        content = todo.get('content', '')
        if content:
            # Run log-task.sh for each todo
            subprocess.run(['bash', f'{script_dir}/log-task.sh', status, content],
                         capture_output=True, timeout=5)
except:
    pass
" "$SCRIPT_DIR" 2>/dev/null &
fi

# Silent output (no injection needed)
exit 0  # Silent exit - suppressOutput is in settings.json

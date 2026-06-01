#!/bin/bash
# Sync TodoWrite status with capsule tasks
# Usage: After using TodoWrite, call this to sync tasks
# Can also be called with task list as JSON

set -euo pipefail
source ".claude/lib/session-env.sh"

TASK_FILE="$(session_path 'current_tasks.log')"

# Clear existing tasks
> "$TASK_FILE"

# If called with JSON argument, parse it
if [ $# -gt 0 ]; then
  # Parse JSON array of tasks
  # Format: [{"content": "...", "status": "..."}, ...]
  echo "$1" | python3 -c "
import sys, json
try:
    tasks = json.load(sys.stdin)
    for task in tasks:
        status = task.get('status', 'pending')
        content = task.get('content', '')
        print(f\"{status}|{content}\")
except:
    pass
" >> "$TASK_FILE"
else
  # Interactive mode - prompt for tasks
  echo "Enter tasks (status|content), empty line to finish:" >&2
  while IFS='|' read -r status content; do
    [ -z "$status" ] && break
    echo "$status|$content" >> "$TASK_FILE"
  done
fi

echo "✓ TodoWrite synced with capsule" >&2

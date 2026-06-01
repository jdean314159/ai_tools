#!/bin/bash

# Inject Capsule - Convert capsule.toon to context for Claude
# Uses hash-based change detection to skip if unchanged

WORKER_PROFILE="${CLAUDE_WORKER_PROFILE:-default}"
SESSION_ID="${CLAUDE_SESSION_ID:-$WORKER_PROFILE}"
SESSION_DIR=".claude/sessions/$SESSION_ID"
CAPSULE_FILE="$SESSION_DIR/capsule.toon"
HASH_FILE="$SESSION_DIR/capsule.hash"

# Update capsule first
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEW_HASH=$(bash "$SCRIPT_DIR/update-capsule.sh" 2>/dev/null)

# Check if changed
OLD_HASH=""
[ -f "$HASH_FILE" ] && OLD_HASH=$(cat "$HASH_FILE" 2>/dev/null)

if [ "$NEW_HASH" = "$OLD_HASH" ] && [ -n "$OLD_HASH" ]; then
  # No change, output empty (no injection needed)
  echo ""
  exit 0
fi

# Save new hash
echo "$NEW_HASH" > "$HASH_FILE"

# Read and convert capsule to readable format
[ ! -f "$CAPSULE_FILE" ] && exit 0

# Export for Python
export SESSION_DIR

python3 << 'PYTHON_SCRIPT'
import os
import sys

session_dir = os.environ.get('SESSION_DIR', '.claude/sessions/default')
capsule_file = f"{session_dir}/capsule.toon"

if not os.path.exists(capsule_file):
    sys.exit(0)

with open(capsule_file, 'r') as f:
    lines = f.readlines()

output = []
current_section = None

for line in lines:
    line = line.rstrip()
    if not line:
        continue
    
    if line.startswith('#capsule'):
        continue
    elif line.startswith('@meta'):
        # Parse: @meta profile=X ts=Y
        parts = line.split()
        output.append('<capsule-meta>')
        for p in parts[1:]:
            if '=' in p:
                k, v = p.split('=', 1)
                output.append(f"  {k}: {v}")
        output.append('</capsule-meta>')
    elif line.startswith('@git'):
        # Parse: @git branch=X changes=Y
        parts = line.split()
        output.append('<git-state>')
        for p in parts[1:]:
            if '=' in p:
                k, v = p.split('=', 1)
                output.append(f"  {k}: {v}")
        output.append('</git-state>')
    elif line.startswith('@files'):
        current_section = 'files'
        output.append('<files-in-context>')
    elif line.startswith('@discoveries'):
        if current_section == 'files':
            output.append('</files-in-context>')
        current_section = 'discoveries'
        output.append('<team-discoveries>')
    elif line.startswith('@tasks'):
        if current_section == 'discoveries':
            output.append('</team-discoveries>')
        current_section = 'tasks'
        output.append('<team-tasks>')
    elif line.startswith('  '):
        # Content line: action:profile:data
        content = line.strip()
        if ':' in content:
            parts = content.split(':', 2)
            if len(parts) >= 3:
                code, profile, data = parts[0], parts[1], parts[2]
                if current_section == 'files':
                    action = {'r': 'read', 'e': 'edit', 'w': 'write'}.get(code, code)
                    output.append(f"  [{profile}] {action}: {data}")
                elif current_section == 'discoveries':
                    cat = {'p': 'pattern', 'i': 'insight', 'd': 'decision', 
                           'a': 'architecture', 'b': 'bug', 'o': 'optimization',
                           'A': 'achievement'}.get(code, code)
                    output.append(f"  [{profile}] {cat}: {data}")
                elif current_section == 'tasks':
                    status = {'P': 'pending', 'I': 'in_progress', 'C': 'completed'}.get(code, code)
                    output.append(f"  [{profile}] {status}: {data}")

# Close last section
if current_section == 'files':
    output.append('</files-in-context>')
elif current_section == 'discoveries':
    output.append('</team-discoveries>')
elif current_section == 'tasks':
    output.append('</team-tasks>')

print('\n'.join(output))
PYTHON_SCRIPT

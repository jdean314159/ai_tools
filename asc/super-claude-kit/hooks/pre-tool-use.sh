#!/bin/bash

# Pre-Tool-Use Hook (Pure Bash - WSL Compatible)
# Runs BEFORE each tool call
# - Blocks large file reads (>50KB) - suggests progressive-reader
# - Warns before redundant file reads (<5 min ago)
# - Enforces dependency tools over Task/Explore
#
# When suppressOutput is in settings.json:
# - Normal case: exit silently (no output)
# - Block/warn: output JSON decision

# Suppress stderr to avoid display issues
exec 2>/dev/null

# Read input from stdin
INPUT=$(cat)

# Get session info
WORKER_PROFILE="${CLAUDE_WORKER_PROFILE:-default}"
SESSION_ID="${CLAUDE_SESSION_ID:-$WORKER_PROFILE}"
SESSION_DIR=".claude/sessions/$SESSION_ID"

mkdir -p "$SESSION_DIR" 2>/dev/null

# Parse tool info using Python
TOOL_INFO=$(echo "$INPUT" | python3 -c "
import sys
import json

try:
    data = json.load(sys.stdin)
    tool_name = data.get('tool_name', '')
    tool_input = data.get('tool_input', {})

    # Extract relevant fields
    file_path = tool_input.get('file_path', tool_input.get('path', ''))
    prompt = tool_input.get('prompt', '')
    subagent = tool_input.get('subagent_type', '')

    print(f'{tool_name}|{file_path}|{prompt}|{subagent}')
except:
    print('|||')
" 2>/dev/null || echo "|||")

TOOL_NAME=$(echo "$TOOL_INFO" | cut -d'|' -f1)
FILE_PATH=$(echo "$TOOL_INFO" | cut -d'|' -f2)
PROMPT=$(echo "$TOOL_INFO" | cut -d'|' -f3)
SUBAGENT=$(echo "$TOOL_INFO" | cut -d'|' -f4)

# === LARGE FILE BLOCKING ===
if [ "$TOOL_NAME" = "Read" ] && [ -n "$FILE_PATH" ] && [ -f "$FILE_PATH" ]; then
  FILE_SIZE=$(wc -c < "$FILE_PATH" 2>/dev/null || echo "0")
  FILE_SIZE_KB=$((FILE_SIZE / 1024))

  if [ "$FILE_SIZE_KB" -gt 50 ]; then
    # Block - must output JSON
    python3 -c "
import json
print(json.dumps({
    'decision': 'block',
    'reason': 'File is ${FILE_SIZE_KB}KB (>50KB limit). Use progressive-reader instead: .claude/bin/progressive-reader --path \"$FILE_PATH\" --list'
}))
" 2>/dev/null || echo '{"decision":"block","reason":"File too large"}'
    exit 0
  fi
fi

# === REDUNDANT READ WARNING ===
if [ "$TOOL_NAME" = "Read" ] && [ -n "$FILE_PATH" ]; then
  FILE_ACCESS_LOG="$SESSION_DIR/file_access.log"
  if [ -f "$FILE_ACCESS_LOG" ]; then
    NOW=$(date +%s)
    FIVE_MIN_AGO=$((NOW - 300))

    RECENT_READ=$(python3 -c "
import sys
import json

file_path = sys.argv[1]
cutoff = int(sys.argv[2])

with open(sys.argv[3], 'r') as f:
    for line in f:
        try:
            entry = json.loads(line.strip())
            if entry.get('path') == file_path and entry.get('timestamp', 0) >= cutoff:
                print('yes')
                sys.exit(0)
        except:
            pass
print('no')
" "$FILE_PATH" "$FIVE_MIN_AGO" "$FILE_ACCESS_LOG" 2>/dev/null || echo "no")

    if [ "$RECENT_READ" = "yes" ]; then
      # Warn - output JSON
      python3 -c "
import json
print(json.dumps({
    'decision': 'warn',
    'message': 'This file was read within the last 5 minutes. Check <files-in-context> in capsule before re-reading.'
}))
" 2>/dev/null || echo '{"decision":"warn","message":"File recently read"}'
      exit 0
    fi
  fi
fi

# === DEPENDENCY TOOL ENFORCEMENT ===
if [ "$TOOL_NAME" = "Task" ]; then
  PROMPT_LOWER=$(echo "$PROMPT" | tr '[:upper:]' '[:lower:]')

  if echo "$PROMPT_LOWER" | grep -qE "(import|depend|who uses|what uses|circular|dead code|unused)"; then
    SUGGESTION=""

    if echo "$PROMPT_LOWER" | grep -qE "(import|depend|who uses|what uses)"; then
      SUGGESTION="Use: bash .claude/tools/query-deps/query-deps.sh <file-path>"
    elif echo "$PROMPT_LOWER" | grep -qE "circular"; then
      SUGGESTION="Use: bash .claude/tools/find-circular/find-circular.sh"
    elif echo "$PROMPT_LOWER" | grep -qE "(dead code|unused)"; then
      SUGGESTION="Use: bash .claude/tools/find-dead-code/find-dead-code.sh"
    fi

    if [ -n "$SUGGESTION" ]; then
      # Warn - output JSON
      python3 -c "
import json
import sys
print(json.dumps({
    'decision': 'warn',
    'message': f'Dependency queries should use specialized tools. {sys.argv[1]}'
}))
" "$SUGGESTION" 2>/dev/null || echo '{"decision":"warn","message":"Use dependency tools"}'
      exit 0
    fi
  fi
fi

# Normal case - exit silently (suppressOutput is in settings.json)
exit 0

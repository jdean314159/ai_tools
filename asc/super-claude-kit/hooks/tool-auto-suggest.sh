#!/usr/bin/env bash
# Tool auto-suggest - suggests relevant tools based on user prompt keywords
# Integrated into pre-task-analysis hook for automatic tool recommendations
#
# IMPORTANT: This hook should only be called from UserPromptSubmit context
# where plain text output IS allowed and added as context.
# If called from other hook contexts, it will corrupt the UI.
#
# The hook now outputs valid JSON for safe integration.

# Redirect stderr to log file
exec 2>>.claude/hook-errors.log

USER_PROMPT="${1:-}"

if [ -z "$USER_PROMPT" ]; then
    exit 0
fi

PROMPT_LOWER=$(echo "$USER_PROMPT" | tr '[:upper:]' '[:lower:]')

declare -a SUGGESTIONS=()

if echo "$PROMPT_LOWER" | grep -qE '(depend|import|require|reference|use)'; then
    SUGGESTIONS+=("query-deps: Query file dependencies")
fi

if echo "$PROMPT_LOWER" | grep -qE '(circular|cycle|loop|recursive depend)'; then
    SUGGESTIONS+=("find-circular: Detect dependency cycles")
fi

if echo "$PROMPT_LOWER" | grep -qE '(unused|dead code|orphan|unreferenced|not used)'; then
    SUGGESTIONS+=("find-dead-code: Find unused files")
fi

if echo "$PROMPT_LOWER" | grep -qE '(impact|affect|break|change.*will|what if|consequence)'; then
    SUGGESTIONS+=("impact-analysis: Analyze change impact")
fi

if echo "$PROMPT_LOWER" | grep -qE '(refactor|restructure|reorganize|move.*file|rename)'; then
    if ! echo "${SUGGESTIONS[*]:-}" | grep -q "query-deps"; then
        SUGGESTIONS+=("query-deps: Check deps before refactoring")
    fi
    if ! echo "${SUGGESTIONS[*]:-}" | grep -q "impact-analysis"; then
        SUGGESTIONS+=("impact-analysis: Understand refactoring impact")
    fi
fi

if echo "$PROMPT_LOWER" | grep -qE '(large file|big file|huge file|read.*entire|bundle|compiled|minified)'; then
    SUGGESTIONS+=("progressive-reader: Read large files efficiently")
fi

if [ ${#SUGGESTIONS[@]} -gt 0 ]; then
    # Build suggestions as a single line for JSON
    TOOL_LIST=""
    for suggestion in "${SUGGESTIONS[@]}"; do
        if [ -n "$TOOL_LIST" ]; then
            TOOL_LIST="$TOOL_LIST, $suggestion"
        else
            TOOL_LIST="$suggestion"
        fi
    done

    # Output valid JSON for UserPromptSubmit hook context
    python3 -c "
import json
import sys
tools = sys.argv[1] if len(sys.argv) > 1 else ''
if tools:
    context = f'[Super Claude Kit] Suggested tools for this task: {tools}. Use: bash ./.claude/lib/tool-runner.sh <tool-name> [args]'
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'UserPromptSubmit',
            'additionalContext': context
        }
    }))
" "$TOOL_LIST" 2>/dev/null || exit 0
fi

exit 0

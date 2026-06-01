#!/bin/bash
# Universal hook runner for Super Claude Kit
# Usage: run-hook.sh <hook-name> [args...]
#
# This script:
# 1. Finds the .claude directory (walks up from pwd)
# 2. Changes to the project root
# 3. Runs the specified hook with proper environment
#
# CRITICAL: This script must not output anything on failure
# as it would corrupt the JSON output expected by Claude

HOOK_NAME="${1:-}"
shift 2>/dev/null || true

# Silent exit if no hook specified
[ -z "$HOOK_NAME" ] && exit 0

# Find project root by looking for .claude directory
find_project_root() {
    local dir="$PWD"

    # Handle Windows paths
    case "$OSTYPE" in
        msys*|cygwin*|win32*)
            dir=$(cygpath -u "$dir" 2>/dev/null || echo "$dir")
            ;;
    esac

    while [ "$dir" != "/" ] && [ -n "$dir" ]; do
        [ -d "$dir/.claude" ] && echo "$dir" && return 0

        local parent=$(dirname "$dir")
        # Stop if we're at root or not making progress
        [ "$parent" = "$dir" ] && break
        dir="$parent"

        # Handle Windows drive roots
        [[ "$dir" =~ ^[A-Za-z]:/?$ ]] && break
    done

    return 1
}

PROJECT_ROOT=$(find_project_root 2>/dev/null)

# Silent exit if no .claude directory found
[ -z "$PROJECT_ROOT" ] && exit 0

cd "$PROJECT_ROOT" 2>/dev/null || exit 0

HOOK_SCRIPT=".claude/hooks/${HOOK_NAME}"

# Silent exit if hook doesn't exist
[ ! -f "$HOOK_SCRIPT" ] && exit 0

# Make executable if needed
[ ! -x "$HOOK_SCRIPT" ] && chmod +x "$HOOK_SCRIPT" 2>/dev/null

# Run the hook
exec "$HOOK_SCRIPT" "$@"

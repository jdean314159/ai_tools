#!/bin/bash
#
# Interactive worker selection for Super Claude Kit
# Prompts user to select a worker profile, then launches Claude with the appropriate
# environment variables set. Supports parallel workers in different terminal windows.
# Sets the terminal tab title to the worker's preferred_name.
#
# Usage:
#   ./select-worker.sh              # Interactive menu
#   ./select-worker.sh backend      # Quick select by partial name
#   ./select-worker.sh 2            # Quick select by number
#   ./select-worker.sh --list       # Just list available workers

set -e

WORKERS_DIR=".claude/workers"
GLOBAL_WORKERS_DIR="$HOME/.claude/workers"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

# Parse worker-identity from markdown frontmatter
get_worker_identity() {
    local file="$1"
    local default_name="$2"

    if [ ! -f "$file" ]; then
        echo "$default_name||"  # name|preferred|mailbox
        return
    fi

    # Extract from worker-identity block in YAML frontmatter
    local frontmatter=$(sed -n '/^---$/,/^---$/p' "$file" 2>/dev/null | grep -A20 'worker-identity:')

    local preferred=$(echo "$frontmatter" | grep 'preferred_name:' | head -1 | sed 's/.*preferred_name:[[:space:]]*//' | tr -d '\r')
    local mailbox=$(echo "$frontmatter" | grep 'mailbox:' | head -1 | sed 's/.*mailbox:[[:space:]]*//' | tr -d '\r')

    echo "${preferred:-$default_name}|${mailbox:-}"
}

get_preferred_name() {
    local file="$1"
    local default_name="$2"
    get_worker_identity "$file" "$default_name" | cut -d'|' -f1
}

get_available_workers() {
    local workers=()

    # Check local project workers first
    if [ -d "$WORKERS_DIR" ]; then
        for file in "$WORKERS_DIR"/*.md; do
            [ -f "$file" ] || continue
            local name=$(basename "$file" .md)
            [ "$name" = "README" ] && continue
            local identity=$(get_worker_identity "$file" "$name")
            local preferred=$(echo "$identity" | cut -d'|' -f1)
            local mailbox=$(echo "$identity" | cut -d'|' -f2)
            workers+=("$name|$file|project|$preferred|$mailbox")
        done

        # Also check subdirectories (worker/role.md pattern)
        for dir in "$WORKERS_DIR"/*/; do
            [ -d "$dir" ] || continue
            local name=$(basename "$dir")
            local worker_file=""
            if [ -f "$dir/role.md" ]; then
                worker_file="$dir/role.md"
            elif [ -f "$dir/config.md" ]; then
                worker_file="$dir/config.md"
            fi
            if [ -n "$worker_file" ]; then
                local identity=$(get_worker_identity "$worker_file" "$name")
                local preferred=$(echo "$identity" | cut -d'|' -f1)
                local mailbox=$(echo "$identity" | cut -d'|' -f2)
                workers+=("$name|$worker_file|project|$preferred|$mailbox")
            fi
        done
    fi

    # Check global workers
    if [ -d "$GLOBAL_WORKERS_DIR" ]; then
        for file in "$GLOBAL_WORKERS_DIR"/*.md; do
            [ -f "$file" ] || continue
            local name=$(basename "$file" .md)
            [ "$name" = "README" ] && continue

            # Skip if already in local list
            local exists=false
            for w in "${workers[@]}"; do
                local wname=$(echo "$w" | cut -d'|' -f1)
                [ "$wname" = "$name" ] && exists=true && break
            done
            if ! $exists; then
                local identity=$(get_worker_identity "$file" "$name")
                local preferred=$(echo "$identity" | cut -d'|' -f1)
                local mailbox=$(echo "$identity" | cut -d'|' -f2)
                workers+=("$name|$file|global|$preferred|$mailbox")
            fi
        done
    fi

    # Sort and output (format: name|file|source|preferred|mailbox)
    printf '%s\n' "${workers[@]}" | sort
}

show_menu() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  Super Claude Kit - Worker Selection${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    local i=1
    while IFS='|' read -r name path source preferred; do
        [ -z "$name" ] && continue
        local tag=""
        [ "$source" = "global" ] && tag=" ${GRAY}(global)${NC}"
        local display="$name"
        if [ -n "$preferred" ] && [ "$preferred" != "$name" ]; then
            display="$name -> $preferred"
        fi
        echo -e "  ${WHITE}[$i]${NC} $display$tag"
        ((i++))
    done <<< "$1"

    echo ""
    echo -e "  ${GRAY}[0] Default (no specific worker)${NC}"
    echo -e "  ${GRAY}[q] Quit${NC}"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

new_session_id() {
    local profile="$1"
    local timestamp=$(date +%s)
    local suffix=$RANDOM
    echo "${profile}-${timestamp}-${suffix}"
}

set_terminal_title() {
    local title="$1"

    # Set terminal title using ANSI escape sequences
    # Works in most terminals (xterm, iTerm2, Terminal.app, Windows Terminal, etc.)
    printf '\033]0;%s\007' "$title"

    # Also try OSC 9;9 for Windows Terminal tab title
    if [ -n "${WT_SESSION:-}" ]; then
        printf '\033]9;9;%s\033\\' "$title"
    fi
}

get_temp_prefix() {
    local profile="$1"
    local mailbox="$2"

    # Use mailbox if available, otherwise profile name
    local base="${mailbox:-$profile}"
    # Slugify: lowercase, replace non-alphanumeric with underscore
    local slug=$(echo "$base" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_' | sed 's/^_//;s/_$//')
    echo "${slug:-worker}"
}

launch_claude() {
    local profile="$1"
    local preferred="$2"
    local mailbox="${3:-}"
    shift 3 2>/dev/null || shift 2

    export CLAUDE_WORKER_PROFILE="$profile"
    export CLAUDE_SESSION_ID=$(new_session_id "$profile")

    # Set session directory path
    export CLAUDE_SESSION_DIR=".claude/sessions/$CLAUDE_SESSION_ID"

    # Set temp file prefix for this worker
    export CLAUDE_WORKER_TEMP_PREFIX=$(get_temp_prefix "$profile" "$mailbox")

    # Set terminal title to preferred name and store in env var for hooks to use
    local title="${preferred:-$profile}"
    export CLAUDE_TERMINAL_TITLE="$title"
    set_terminal_title "$title"

    echo ""
    echo -e "${GREEN}Launching Claude with worker: $profile${NC}"
    echo -e "${GRAY}Session ID: $CLAUDE_SESSION_ID${NC}"
    echo -e "${GRAY}Session Dir: $CLAUDE_SESSION_DIR${NC}"
    echo -e "${GRAY}Temp Prefix: $CLAUDE_WORKER_TEMP_PREFIX${NC}"
    echo ""

    exec claude "$@"
}

# Parse arguments
QUICK_SELECT=""
LIST_ONLY=false
CLAUDE_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --list|-l)
            LIST_ONLY=true
            shift
            ;;
        --help|-h)
            echo "Usage: select-worker.sh [OPTIONS] [WORKER] [-- CLAUDE_ARGS...]"
            echo ""
            echo "Options:"
            echo "  --list, -l    List available workers and exit"
            echo "  --help, -h    Show this help message"
            echo ""
            echo "Examples:"
            echo "  select-worker.sh              # Interactive menu"
            echo "  select-worker.sh backend      # Quick select by partial name"
            echo "  select-worker.sh 2            # Quick select by number"
            echo "  select-worker.sh backend -- --verbose  # Pass args to claude"
            exit 0
            ;;
        --)
            shift
            CLAUDE_ARGS=("$@")
            break
            ;;
        *)
            if [ -z "$QUICK_SELECT" ]; then
                QUICK_SELECT="$1"
            else
                CLAUDE_ARGS+=("$1")
            fi
            shift
            ;;
    esac
done

# Get available workers
WORKERS=$(get_available_workers)
WORKER_COUNT=$(echo "$WORKERS" | grep -c '|' || echo 0)

if [ "$WORKER_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}No worker profiles found.${NC}"
    echo -e "${YELLOW}Create workers in .claude/workers/ or ~/.claude/workers/${NC}"
    echo ""
    echo -e "${CYAN}Launching Claude with default profile...${NC}"
    set_terminal_title "Claude (default)"
    exec claude "${CLAUDE_ARGS[@]}"
fi

# List mode
if $LIST_ONLY; then
    echo ""
    echo -e "${CYAN}Available Workers:${NC}"
    echo ""
    while IFS='|' read -r name path source preferred; do
        [ -z "$name" ] && continue
        tag=""
        [ "$source" = "global" ] && tag=" (global)"
        display="$name"
        if [ -n "$preferred" ] && [ "$preferred" != "$name" ]; then
            display="$name (title: $preferred)"
        fi
        echo "  - $display$tag"
    done <<< "$WORKERS"
    echo ""
    exit 0
fi

# Quick select mode
if [ -n "$QUICK_SELECT" ]; then
    # Try as number first
    if [[ "$QUICK_SELECT" =~ ^[0-9]+$ ]]; then
        SELECTED=$(echo "$WORKERS" | sed -n "${QUICK_SELECT}p")
        if [ -n "$SELECTED" ]; then
            PROFILE=$(echo "$SELECTED" | cut -d'|' -f1)
            PREFERRED=$(echo "$SELECTED" | cut -d'|' -f4)
            MAILBOX=$(echo "$SELECTED" | cut -d'|' -f5)
            launch_claude "$PROFILE" "$PREFERRED" "$MAILBOX" "${CLAUDE_ARGS[@]}"
        fi
    fi

    # Try as partial name match
    SELECTED=$(echo "$WORKERS" | grep -i "$QUICK_SELECT" | head -1)
    if [ -n "$SELECTED" ]; then
        PROFILE=$(echo "$SELECTED" | cut -d'|' -f1)
        PREFERRED=$(echo "$SELECTED" | cut -d'|' -f4)
        MAILBOX=$(echo "$SELECTED" | cut -d'|' -f5)
        launch_claude "$PROFILE" "$PREFERRED" "$MAILBOX" "${CLAUDE_ARGS[@]}"
    fi

    echo -e "${RED}No worker found matching: $QUICK_SELECT${NC}"
    echo ""
fi

# Interactive menu
show_menu "$WORKERS"

read -p "Select worker: " selection

case "$selection" in
    q|Q)
        echo -e "${YELLOW}Cancelled.${NC}"
        exit 0
        ;;
    0)
        echo -e "${CYAN}Launching Claude with default profile...${NC}"
        set_terminal_title "Claude (default)"
        exec claude "${CLAUDE_ARGS[@]}"
        ;;
    [0-9]*)
        SELECTED=$(echo "$WORKERS" | sed -n "${selection}p")
        if [ -n "$SELECTED" ]; then
            PROFILE=$(echo "$SELECTED" | cut -d'|' -f1)
            PREFERRED=$(echo "$SELECTED" | cut -d'|' -f4)
            MAILBOX=$(echo "$SELECTED" | cut -d'|' -f5)
            launch_claude "$PROFILE" "$PREFERRED" "$MAILBOX" "${CLAUDE_ARGS[@]}"
        else
            echo -e "${RED}Invalid selection: $selection${NC}"
            exit 1
        fi
        ;;
    *)
        echo -e "${RED}Invalid selection: $selection${NC}"
        exit 1
        ;;
esac

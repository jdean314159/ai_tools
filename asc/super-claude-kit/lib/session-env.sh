#!/bin/bash
# Shared helper for session-scoped state files.
# Works on Windows (Git Bash, WSL, MSYS2), macOS, and Linux.

# Prevent multiple initialization
if [ -n "${SCK_SESSION_ENV_INITIALIZED:-}" ]; then
  return 0 2>/dev/null || exit 0
fi

# Detect Windows environment
detect_windows() {
  case "$OSTYPE" in
    msys*|cygwin*|win32*) return 0 ;;
  esac
  [ -n "${WINDIR:-}" ] && return 0
  return 1
}

# Convert Windows path to Unix-style if needed
normalize_path() {
  local path="$1"
  if detect_windows && command -v cygpath >/dev/null 2>&1; then
    cygpath -u "$path" 2>/dev/null || echo "$path"
  else
    echo "$path"
  fi
}

# Get a cross-platform timestamp
get_timestamp() {
  date +%s 2>/dev/null || python3 -c "import time; print(int(time.time()))" 2>/dev/null || echo "0"
}

# Get MD5 hash (works on macOS, Linux, and Windows)
get_md5() {
  local file="$1"
  if command -v md5sum >/dev/null 2>&1; then
    md5sum "$file" 2>/dev/null | cut -d' ' -f1
  elif command -v md5 >/dev/null 2>&1; then
    md5 -q "$file" 2>/dev/null
  else
    # Fallback to Python
    python3 -c "import hashlib; print(hashlib.md5(open('$file', 'rb').read()).hexdigest())" 2>/dev/null || echo "unknown"
  fi
}

# Get file size in bytes (cross-platform)
get_file_size() {
  local file="$1"
  if [ ! -f "$file" ]; then
    echo "0"
    return
  fi

  # Try stat (Linux style)
  local size=$(stat -c%s "$file" 2>/dev/null)
  if [ -n "$size" ]; then
    echo "$size"
    return
  fi

  # Try stat (macOS/BSD style)
  size=$(stat -f%z "$file" 2>/dev/null)
  if [ -n "$size" ]; then
    echo "$size"
    return
  fi

  # Fallback: wc -c
  size=$(wc -c < "$file" 2>/dev/null | tr -d ' ')
  if [ -n "$size" ]; then
    echo "$size"
    return
  fi

  echo "0"
}

# Build session ID from environment or generate default
_sck_raw_session_id="${CLAUDE_SESSION_ID:-}"
if [ -z "$_sck_raw_session_id" ]; then
  _sck_raw_session_id="${CLAUDE_WORKER_PROFILE:-default}"
fi

# Sanitize to filesystem-friendly slug (works on Windows too)
_sck_session_id=$(
  printf '%s' "$_sck_raw_session_id" |
    tr '[:upper:]' '[:lower:]' |
    tr -cs 'a-z0-9._-' '-' |
    sed -E 's/^-+//; s/-+$//'
)

if [ -z "$_sck_session_id" ]; then
  _sck_session_id="session"
fi

export CLAUDE_SESSION_ID="$_sck_session_id"
export CLAUDE_SESSION_DIR=".claude/sessions/$CLAUDE_SESSION_ID"

# Create session directory (handle Windows path issues)
mkdir -p "$CLAUDE_SESSION_DIR" 2>/dev/null || true

# Helper function to get session-scoped file path
session_path() {
  local rel="$1"
  printf '%s/%s' "$CLAUDE_SESSION_DIR" "$rel"
}

# Export utility functions for use by hooks
export -f detect_windows 2>/dev/null || true
export -f normalize_path 2>/dev/null || true
export -f get_timestamp 2>/dev/null || true
export -f get_md5 2>/dev/null || true
export -f get_file_size 2>/dev/null || true
export -f session_path 2>/dev/null || true

SCK_SESSION_ENV_INITIALIZED=1
export SCK_SESSION_ENV_INITIALIZED

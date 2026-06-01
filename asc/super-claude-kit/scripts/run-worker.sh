#!/bin/bash
# Helper to launch Claude with an isolated Super Claude Kit session.

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: bash .claude/scripts/run-worker.sh <worker-profile> [session-id]" >&2
  exit 1
fi

PROFILE="$1"
shift || true

if [ $# -ge 1 ]; then
  SESSION_ID="$1"
else
  SESSION_ID="${PROFILE}-$(date +%s)-$RANDOM"
fi

export CLAUDE_WORKER_PROFILE="$PROFILE"
export CLAUDE_SESSION_ID="$SESSION_ID"

echo "🚀 Launching Claude with worker '$PROFILE' (session: $SESSION_ID)" >&2
exec claude "$@"

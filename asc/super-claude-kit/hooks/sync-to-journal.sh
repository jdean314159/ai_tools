#!/bin/bash
# Sync Capsule Discoveries to Exploration Journal
# Appends important discoveries from current session to journal

set -euo pipefail
source ".claude/lib/session-env.sh"

JOURNAL_DIR="docs/exploration"
CURRENT_SESSION="$JOURNAL_DIR/CURRENT_SESSION.md"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
DISCOVERY_LOG="$(session_path 'session_discoveries.log')"

# Check if journal directory exists
if [ ! -d "$JOURNAL_DIR" ]; then
  mkdir -p "$JOURNAL_DIR"
fi

# Check if we have discoveries to sync
if [ ! -f "$DISCOVERY_LOG" ] || [ ! -s "$DISCOVERY_LOG" ]; then
  exit 0  # No discoveries to sync
fi

# Create or append to current session file
if [ ! -f "$CURRENT_SESSION" ]; then
  cat > "$CURRENT_SESSION" << EOF
# Current Session: Context Capsule Integration
**Date**: $(date '+%B %d, %Y')

---

## Session Discoveries

EOF
fi

# Check if we already have a "Context Capsule Session" section
if ! grep -q "### Session: $TIMESTAMP" "$CURRENT_SESSION" 2>/dev/null; then
  echo "" >> "$CURRENT_SESSION"
  echo "### Session: $TIMESTAMP" >> "$CURRENT_SESSION"
  echo "" >> "$CURRENT_SESSION"
fi

# Append discoveries
echo "**Discoveries from this session:**" >> "$CURRENT_SESSION"
echo "" >> "$CURRENT_SESSION"

# Read and format discoveries
while IFS=',' read -r ts category content; do
  # Category formatting
  case "$category" in
    "pattern")
      echo "- 🔍 **Pattern**: $content" >> "$CURRENT_SESSION"
      ;;
    "insight")
      echo "- 💭 **Insight**: $content" >> "$CURRENT_SESSION"
      ;;
    "decision")
      echo "- 🎯 **Decision**: $content" >> "$CURRENT_SESSION"
      ;;
    "architecture")
      echo "- 🏗️ **Architecture**: $content" >> "$CURRENT_SESSION"
      ;;
    "bug")
      echo "- 🐛 **Bug**: $content" >> "$CURRENT_SESSION"
      ;;
    "optimization")
      echo "- ⚡ **Optimization**: $content" >> "$CURRENT_SESSION"
      ;;
    *)
      echo "- 📝 **$category**: $content" >> "$CURRENT_SESSION"
      ;;
  esac
done < "$DISCOVERY_LOG"

echo "" >> "$CURRENT_SESSION"
echo "---" >> "$CURRENT_SESSION"
echo "" >> "$CURRENT_SESSION"

echo "✓ Discoveries synced to exploration journal" >&2

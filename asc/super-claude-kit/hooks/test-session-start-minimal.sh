#!/bin/bash
# Minimal SessionStart test - demonstrates proper JSON output
#
# IMPORTANT: SessionStart hooks can use plain text (added to context)
# but JSON format is preferred for consistency.

# Redirect stderr to log file
exec 2>>.claude/hook-errors.log

# Output proper JSON for SessionStart
python3 -c "
import json
from datetime import datetime

print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'SessionStart',
        'additionalContext': f'TEST: SessionStart hook loaded at {datetime.now().isoformat()}'
    }
}))
" 2>/dev/null || echo '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"TEST: SessionStart hook loaded"}}'

exit 0

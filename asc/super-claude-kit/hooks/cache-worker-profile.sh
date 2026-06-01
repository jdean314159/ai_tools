#!/bin/bash
# Cache worker profile metadata (identity, mailbox, temp prefix) from frontmatter.

# Redirect stderr to prevent display corruption
exec 2>>.claude/hook-errors.log

PROFILE_NAME="${1:-default}"
WORKER_FILE="${2:-}"

# Build default output path if not provided
if [ -n "${3:-}" ]; then
    OUTPUT_FILE="$3"
else
    SESSION_ID="${CLAUDE_SESSION_ID:-${CLAUDE_WORKER_PROFILE:-default}}"
    OUTPUT_FILE=".claude/sessions/$SESSION_ID/current_worker_identity.json"
fi

mkdir -p "$(dirname "$OUTPUT_FILE")" 2>/dev/null || true

if [ -z "$WORKER_FILE" ] || [ ! -f "$WORKER_FILE" ]; then
cat > "$OUTPUT_FILE" <<EOF
{
  "profile": "$PROFILE_NAME",
  "preferred_name": "$PROFILE_NAME",
  "mailbox": "",
  "register_with_agent_mail": false,
  "uses_beads": false,
  "temp_prefix": "$(echo "$PROFILE_NAME" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_')"
}
EOF
  exit 0
fi

python3 - "$PROFILE_NAME" "$WORKER_FILE" "$OUTPUT_FILE" <<'PYTHON'
import json
import pathlib
import re
import sys

profile = sys.argv[1]
worker_path = pathlib.Path(sys.argv[2])
output_path = pathlib.Path(sys.argv[3])

def slugify(value):
    cleaned = re.sub(r'[^a-zA-Z0-9]+', '_', value).strip('_')
    if not cleaned:
        cleaned = profile
    return cleaned.lower()

text = worker_path.read_text(encoding="utf-8", errors="ignore")
frontmatter = ""
if text.startswith("---"):
    parts = text.split("---", 2)
    if len(parts) >= 3:
        frontmatter = parts[1]

# Use a dict to hold mutable state (avoids nonlocal/global issues)
identity = {
    "preferred_name": "",
    "mailbox": "",
    "register": None,
    "uses_beads": None
}
allowed_tools = []

if frontmatter:
    lines = frontmatter.splitlines()
    capture_identity = False
    identity_indent = 0
    capture_tools = False
    tools_indent = 0

    def process_identity_line(line, state):
        """Process a line within the worker-identity block."""
        if ":" not in line:
            return
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not value:
            return
        low = value.lower()
        if key == "preferred_name":
            state["preferred_name"] = value
        elif key == "mailbox":
            state["mailbox"] = value
        elif key == "register_with_agent_mail":
            if low in ("true", "false"):
                state["register"] = (low == "true")
        elif key == "uses_beads":
            if low in ("true", "false"):
                state["uses_beads"] = (low == "true")

    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(raw) - len(raw.lstrip())

        if capture_identity and indent > identity_indent:
            process_identity_line(stripped, identity)
            continue
        elif capture_identity and indent <= identity_indent:
            capture_identity = False

        if capture_tools and indent > tools_indent:
            if stripped.startswith("-"):
                item = stripped[1:].strip().strip('"').strip("'")
                if item:
                    allowed_tools.append(item)
            continue
        elif capture_tools and indent <= tools_indent:
            capture_tools = False

        if indent == 0 and stripped.startswith("worker-identity"):
            capture_identity = True
            identity_indent = indent
            continue

        if indent == 0 and stripped.lower().startswith("tools:"):
            value = stripped.split(":", 1)[1].strip()
            if value:
                if value.startswith("[") and value.endswith("]"):
                    value = value[1:-1]
                allowed_tools.extend(
                    [item.strip().strip('"').strip("'") for item in value.split(",") if item.strip()]
                )
            else:
                capture_tools = True
                tools_indent = indent
            continue

payload = {
    "profile": profile,
    "preferred_name": identity["preferred_name"] or profile,
    "mailbox": identity["mailbox"],
    "register_with_agent_mail": bool(identity["register"]) if identity["register"] is not None else False,
    "uses_beads": bool(identity["uses_beads"]) if identity["uses_beads"] is not None else False,
    "allowed_tools": allowed_tools,
    "temp_prefix": slugify(identity["mailbox"] or profile)
}

output_path.write_text(json.dumps(payload, indent=2))
PYTHON

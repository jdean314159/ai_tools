# Worker Profiles

Each Claude CLI window can now load its own worker profile instructions from
`.claude/workers/<profile>.md` (or `<profile>/role.md`). Set the
`CLAUDE_WORKER_PROFILE` environment variable before launching `claude` to pick
which profile to load. The `session-start` and `pre-task-analysis` hooks will
inject the matching file into the session's `systemMessage`, ensuring every
window gets its own long-lived persona while still sharing the same team
memory.

Profiles are installed to `~/.claude/workers/` during setup. Create additional
files in that directory to define new workers (for example,
`~/.claude/workers/backend-developer.md`). Any Markdown content is valid.

## Frontmatter & Identity

Start each worker file with YAML frontmatter so the hooks can parse identity
metadata. Example:

```markdown
---
name: backend-developer
worker-identity:
  preferred_name: BackendDeveloper
  register_with_agent_mail: true
  mailbox: BackendDeveloper
---
```

The SessionStart hook extracts the `worker-identity` block and:

- Displays a reminder (profile, preferred name, Agent Mail mailbox, registration flag, and required temp-file prefix)
- Exports helper variables: `CLAUDE_SESSION_DIR`, `CLAUDE_WORKER_TEMP_PREFIX`, `CLAUDE_AGENT_MAILBOX`, `CLAUDE_WORKER_REGISTER_WITH_MAIL`
- Cleans up `tmp_workermail_${CLAUDE_WORKER_TEMP_PREFIX}_*.json` so temp files stay isolated per worker
- If `register_with_agent_mail: true` and `mailbox` is set, the session automatically launches a session hook (`fetch_inbox MCP tool`). Configure the poll interval via `/.claude/hooks/ack-worker-mail-alert.sh`.
- Set `uses_beads: true` to run `bd quickstart` and `bd ready --json` on every session start. Output is written to `.claude/beads/quickstart.log`, and the latest lines are shown in the worker banner so you immediately see the Beads queue status (make sure `bd` is on `PATH`).
- For `uses_beads: true` workers, logging a `bug` discovery (`./.claude/hooks/log-discovery.sh bug "<details>"`) automatically runs `bd create` (type `bug`, priority 1, labels `bug,auto`) and stores the attempt/outcome in `.claude/beads/bug-issues.log` so the backlog never lags behind the capsule memory.
- Use the top-level `tools:` entry to list the exact Claude Code tools this worker is allowed to call (comma-separated or YAML list). The PreToolUse hook enforces this list-any attempt to call a tool not in `tools:` will be blocked. Leave the field empty to allow all tools.

## Session Folders & Temp Files

Each worker session gets an isolated directory for state and temp files:

```
.claude/sessions/<CLAUDE_SESSION_ID>/
├── current_worker_identity.json   # Parsed identity from frontmatter
├── agent_mail_alert.txt           # Agent Mail notifications (if enabled)
├── session_files.log              # Files accessed this session
├── session_discoveries.log        # Discoveries logged this session
└── tmp_workermail_<prefix>_*.json # Your temp files (auto-cleaned)
```

### Temp File Naming Convention

**ALWAYS** use this pattern for temporary JSON files:

```
tmp_workermail_${CLAUDE_WORKER_TEMP_PREFIX}_<purpose>.json
```

Examples:
- `tmp_workermail_backenddeveloper_register.json` - Agent Mail registration payload
- `tmp_workermail_backenddeveloper_message.json` - Outgoing message draft
- `tmp_workermail_projectmanager_reservation.json` - File reservation request

### Where to Create Temp Files

**Preferred**: Create temp files in your session directory:
```bash
# Session directory is available as CLAUDE_SESSION_DIR
$CLAUDE_SESSION_DIR/tmp_workermail_${CLAUDE_WORKER_TEMP_PREFIX}_register.json
```

**Also works**: Current working directory (project root):
```bash
./tmp_workermail_${CLAUDE_WORKER_TEMP_PREFIX}_register.json
```

Both locations are cleaned at session start and end.

### Why This Matters

- **Isolation**: Multiple workers can run in parallel without file collisions
- **Auto-cleanup**: Hooks remove matching files at session start/end
- **Debugging**: Files are organized per-session for easy inspection

# Quick Setup Guide

This walkthrough shows how to launch a worker profile in the Claude CLI and configure the environment variables the hooks rely on (poller project key, poll interval, etc.).

---

## 1. Install Super Claude Kit

Run the installer in your repo (or the update script if you already installed it):

```bash
bash install
# or later
bash .claude/scripts/update-super-claude.sh
```

This creates the `.claude/` runtime directory (hooks, docs, workers, etc.).

---

## 2. Set Core Environment Variables

| Variable | Purpose | Bash/WSL/macOS | PowerShell | Command Prompt |
| -------- | ------- | -------------- | ---------- | -------------- |
| `CLAUDE_WORKER_PROFILE` | Picks the worker instructions under `.claude/workers/<profile>.md`. Required for per-worker personas. | `export CLAUDE_WORKER_PROFILE=backend-developer` | `$env:CLAUDE_WORKER_PROFILE='backend-developer'` | `set CLAUDE_WORKER_PROFILE=backend-developer` |
| `CLAUDE_SESSION_ID` | Names the per-window session directory (`.claude/sessions/<id>`). Give each terminal a unique id so their logs don't collide. | `export CLAUDE_SESSION_ID=backend-dev-1` | `$env:CLAUDE_SESSION_ID='backend-dev-1'` | `set CLAUDE_SESSION_ID=backend-dev-1` |
| `CLAUDE_AGENT_MAIL_PROJECT_KEY` | Agent Mail project identifier for polling/registration. Defaults to `/project`; override if your Agent Mail server expects something else. | `export CLAUDE_AGENT_MAIL_PROJECT_KEY=/my/team/project` | `$env:CLAUDE_AGENT_MAIL_PROJECT_KEY='/my/team/project'` | `set CLAUDE_AGENT_MAIL_PROJECT_KEY=/my/team/project` |
| Launch command | Combine env vars and start Claude. | `CLAUDE_SESSION_ID=dev1 CLAUDE_WORKER_PROFILE=backend-developer claude` | `$env:CLAUDE_SESSION_ID='dev1'; $env:CLAUDE_WORKER_PROFILE='backend-developer'; claude` | `set CLAUDE_SESSION_ID=dev1 && set CLAUDE_WORKER_PROFILE=backend-developer && claude` |

> **Windows tip:** WSL does not forward custom env vars to `bash` unless they're listed in `WSLENV`. Either run `pwsh -File .claude/scripts/run-worker.ps1 backend-developer dev1` (auto-configures `WSLENV`) or set it yourself once: `setx WSLENV "CLAUDE_WORKER_PROFILE/u:CLAUDE_SESSION_ID/u:CLAUDE_AGENT_MAIL_PROJECT_KEY/u"` and open a new terminal.

- **Helper script**: `bash .claude/scripts/run-worker.sh backend-developer dev1` sets both env vars for you (the session id argument is optional—one is generated when omitted).
- **Multiple windows**: use different `CLAUDE_SESSION_ID` values (or call `run-worker.sh` with different ids) for each terminal. Per-session data lives under `.claude/sessions/<session-id>/`.

---

## 3. Launch the Worker in the CLI

Pick a worker profile from `workers/` (e.g., `backend-developer`, `frontend-developer`, `tests-developer`, `product-manager`, etc.) and run:

```
# Bash/WSL/macOS
CLAUDE_SESSION_ID=dev1 CLAUDE_WORKER_PROFILE=backend-developer claude

# PowerShell
$env:CLAUDE_SESSION_ID='dev1'; $env:CLAUDE_WORKER_PROFILE='backend-developer'; claude

# PowerShell helper (auto WSLENV forwarding)
pwsh -File .claude/scripts/run-worker.ps1 backend-developer dev1

# Command Prompt
set CLAUDE_SESSION_ID=dev1 && set CLAUDE_WORKER_PROFILE=backend-developer && claude

# Or cross-platform helper
bash .claude/scripts/run-worker.sh backend-developer dev1
```

The session banner will:

- Load the worker instructions into the system message.
- Run `bd quickstart` + `bd ready --json` if the profile has `uses_beads: true`.
- Register with Agent Mail and fetch inbox if `register_with_agent_mail: true`.
- Show the inbox summary and Beads ready queue.

---

## 4. Checking Agent Mail

To check for new messages:

1. Use the MCP Agent Mail `fetch_inbox` tool with your agent name.
2. Process the messages as needed.
3. Acknowledge alerts so they don't repeat:

```bash
./.claude/hooks/ack-worker-mail-alert.sh
```

---

## 5. Worker-Specific Steps

Each worker profile documents additional requirements (e.g., registering with Worker Mail, running `bd ready --json`, logging discoveries). Read the profile file in `workers/<name>.md` or review the session banner reminder to confirm:

- Required tooling (Vitest, TestContainers, etc.).
- Mandatory commands at session start.
- Escalation rules (ProductManager vs SoftwareArchitect vs ProjectManager).

---

## 6. Helpful Tips

- **Multiple windows**: export `CLAUDE_WORKER_PROFILE` differently in each terminal to run several workers simultaneously.
- **Custom poll key**: set `CLAUDE_AGENT_MAIL_PROJECT_KEY` once in your shell profile (e.g., `.zshrc`) so all workers use the same value.
- **Troubleshooting**: if Agent Mail isn't working, check that the MCP server is running on port 8765 and walk through [`docs/agent-mail-polling.md`](agent-mail-polling.md).

Once the worker is running, follow its workflow (Beads reservations, file reservations, discovery logging, etc.) and keep the CLI session open until the human or control harness explicitly ends it.

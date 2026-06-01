# Agent Mail Integration Guide

Agent Mail is the coordination channel for Super Claude workers. Workers with `register_with_agent_mail: true` are automatically registered at session start, and their inbox is fetched.

> **Project key**: All examples assume the default `/project`. Override with `CLAUDE_AGENT_MAIL_PROJECT_KEY` if your Agent Mail server expects a different identifier.

---

## How It Works

Super Claude Kit uses a **hook-based delivery model** for Agent Mail:

1. **SessionStart hook** registers the worker and fetches inbox
2. **Initial inbox summary** is included in the session banner
3. **You check for new messages** using the MCP Agent Mail `fetch_inbox` tool
4. **After processing**, acknowledge with `./.claude/hooks/ack-worker-mail-alert.sh`

---

## 1. Registration Sequence

Registration happens automatically at session start for workers with `register_with_agent_mail: true`.

For manual registration or project setup, use these commands:

```bash
PROJECT_KEY="${CLAUDE_AGENT_MAIL_PROJECT_KEY:-/project}"
```

```bash
curl -s http://127.0.0.1:8765/mcp/ -X POST -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"tools/call\",\"id\":1,\"params\":{\"name\":\"ensure_project\",\"arguments\":{\"human_key\":\"${PROJECT_KEY}\"}}}"

curl -s http://127.0.0.1:8765/mcp/ -X POST -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"tools/call\",\"id\":2,\"params\":{\"name\":\"register_agent\",\"arguments\":{\"project_key\":\"${PROJECT_KEY}\",\"program\":\"Claude Code\",\"model\":\"claude-sonnet-4\",\"name\":\"ProjectManager\"}}}"
```

---

## 2. Checking Your Inbox

Use the MCP Agent Mail `fetch_inbox` tool to check for new messages:

```bash
# Via MCP tool (preferred)
# Use the fetch_inbox tool with your agent_name

# Via curl (for debugging)
curl -s http://127.0.0.1:8765/mcp/ -X POST -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"tools/call\",\"id\":1,\"params\":{\"name\":\"fetch_inbox\",\"arguments\":{\"project_key\":\"${PROJECT_KEY}\",\"agent_name\":\"YourWorkerName\",\"limit\":20,\"include_bodies\":true}}}"
```

---

## 3. Acknowledging Alerts

After processing inbox messages, clear the alert:

```bash
./.claude/hooks/ack-worker-mail-alert.sh
```

---

## 4. Sending Messages

Use the MCP Agent Mail `send_message` tool to send messages to other workers:

```bash
# Via MCP tool (preferred)
# Use the send_message tool with recipient, subject, body, etc.
```

---

## 5. Cleanup

Temp files are automatically cleaned at session start/end. If needed, manually clean:

```bash
# Remove alert file
rm -f .claude/sessions/<CLAUDE_SESSION_ID>/agent_mail_alert.txt

# Remove temp files
rm -f .claude/sessions/<CLAUDE_SESSION_ID>/tmp_agentmail_*.json
```

---

## 6. Troubleshooting

| Symptom | Fix |
| ------- | ---- |
| Agent Mail server not responding | Check that the MCP server is running on port 8765 |
| Alerts never clear | Run `ack-worker-mail-alert.sh` after processing |
| Registration fails | Verify the project key and mailbox name in worker frontmatter |

---

Keep this guide handy for Agent Mail configuration and debugging.

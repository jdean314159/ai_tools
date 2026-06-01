# Troubleshooting Guide

Common issues and solutions when using MCP Agent Mail.

## JSON-RPC Format for curl Calls

When calling Agent Mail via curl, you must use the correct JSON-RPC 2.0 wrapper format:

### Correct Structure

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "id": 1,
  "params": {
    "name": "TOOL_NAME_HERE",
    "arguments": {
      // Your actual parameters go here
    }
  }
}
```

### Common Mistakes

| ❌ Wrong                        | ✅ Correct                                                            |
| ------------------------------ | -------------------------------------------------------------------- |
| Put params at root level       | Wrap in `params.arguments`                                           |
| Use `"method": "send_message"` | Use `"method": "tools/call"` with `"name": "send_message"` in params |
| Omit `jsonrpc` or `id`         | Always include both                                                  |
| Use single quotes              | Use double quotes only (JSON spec)                                   |

### Complete curl Example

```bash
# Using a temp file (recommended for Windows/complex payloads)
cat > tmp_send.json << 'EOF'
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "id": 1,
  "params": {
    "name": "send_message",
    "arguments": {
      "project_key": "/excalibur/dispatch",
      "sender_name": "TestsDeveloper",
      "to": ["ProjectManager"],
      "thread_id": "sprint-30",
      "subject": "Status Update",
      "body_md": "Task completed.",
      "importance": "normal",
      "ack_required": true
    }
  }
}
EOF

curl -s http://127.0.0.1:8765/mcp/ -X POST \
  -H "Content-Type: application/json" \
  -d @tmp_send.json
```

### Using printf (Unix/simple payloads)

```bash
printf '{"jsonrpc":"2.0","method":"tools/call","id":1,"params":{"name":"send_message","arguments":{"project_key":"/excalibur/dispatch","sender_name":"TestsDeveloper","to":["ProjectManager"],"thread_id":"sprint-30","subject":"Update","body_md":"Done.","importance":"normal","ack_required":true}}}' | \
  curl -s http://127.0.0.1:8765/mcp/ -X POST -H "Content-Type: application/json" -d @-
```

### Windows PowerShell

```powershell
# Write JSON to temp file to avoid escaping issues
@'
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "id": 1,
  "params": {
    "name": "send_message",
    "arguments": {
      "project_key": "/excalibur/dispatch",
      "sender_name": "TestsDeveloper",
      "to": ["ProjectManager"],
      "thread_id": "sprint-30",
      "subject": "Status Update",
      "body_md": "Task completed.",
      "importance": "normal",
      "ack_required": true
    }
  }
}
'@ | Out-File -Encoding utf8 tmp_send.json

curl -s http://127.0.0.1:8765/mcp/ -X POST -H "Content-Type: application/json" -d "@tmp_send.json"
```

---

## Common Parameter Mistakes

When calling Agent Mail tools directly (especially via curl/JSON-RPC), ensure you use the **exact parameter names**:

### send_message Parameters

| ❌ Wrong      | ✅ Correct     | Notes                      |
| ------------ | ------------- | -------------------------- |
| `from_agent` | `sender_name` | Who is sending the message |
| `to_agent`   | `to`          | Array of recipient names   |
| `body`       | `body_md`     | Markdown message body      |

**Correct Example:**

```json
{
  "project_key": "/excalibur/dispatch",
  "sender_name": "TestsDeveloper",
  "to": ["ProjectManager"],
  "thread_id": "sprint-30",
  "subject": "Status Update",
  "body_md": "Task completed successfully.",
  "importance": "normal",
  "ack_required": true
}
```

### request_contact / respond_contact Parameters

| ❌ Wrong       | ✅ Correct    | Notes                        |
| ------------- | ------------ | ---------------------------- |
| `sender_name` | `from_agent` | Requester identity           |
| `to`          | `to_agent`   | Target agent (single string) |

**Note:** Contact tools use `from_agent`/`to_agent`, while `send_message` uses `sender_name`/`to`. This asymmetry is intentional but easy to confuse.

### fetch_inbox Parameters

| ❌ Wrong       | ✅ Correct    | Notes                  |
| ------------- | ------------ | ---------------------- |
| `sender_name` | `agent_name` | Your agent identity    |
| `count`       | `limit`      | Max messages to return |

---

## Error Messages

### "sender_name not registered"

**Cause**: Attempting to send message before registering agent identity.

**Solution**:

```javascript
// Always register first
register_agent({
  project_key: "D:\\Excalibur.Dispatch",
  program: "Claude Code",
  model: "claude-sonnet-4"
})

// Or use macro
macro_start_session({
  human_key: "/excalibur/dispatch",
  program: "Claude Code",
  model: "claude-sonnet-4"
})
```

### "FILE_RESERVATION_CONFLICT"

**Cause**: Another agent holds exclusive reservation on overlapping paths.

**Solution**:

```javascript
// 1. Check conflicts
const result = file_reservation_paths({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "YourAgent",
  paths: ["src/api/**"],
  exclusive: true
})

if (result.conflicts.length > 0) {
  const conflict = result.conflicts[0]
  console.log(`Conflict with ${conflict.agent_name}`)
  console.log(`Expires: ${conflict.expires_ts}`)

  // Option A: Contact agent
  send_message({
    project_key: "D:\\Excalibur.Dispatch",
    sender_name: "YourAgent",
    to: [conflict.agent_name],
    subject: "Coordination needed for src/api",
    body_md: "I need to work on this area. Can we coordinate?",
    importance: "high"
  })

  // Option B: Use non-exclusive
  file_reservation_paths({
    project_key: "D:\\Excalibur.Dispatch",
    agent_name: "YourAgent",
    paths: ["src/api/**"],
    exclusive: false
  })

  // Option C: Wait for expiry
  // Check expires_ts and retry after
}
```

### "CONTACT_BLOCKED"

**Cause**: Attempting to message agent without established contact when policy requires it.

**Solution**:

```javascript
// Option 1: Request contact manually
request_contact({
  project_key: "D:\\Excalibur.Dispatch",
  from_agent: "YourAgent",
  to_agent: "TheirAgent",
  reason: "Need to coordinate on feature X"
})

// Wait for approval, then send message

// Option 2: Use auto-handshake macro
macro_contact_handshake({
  project_key: "D:\\Excalibur.Dispatch",
  requester: "YourAgent",
  target: "TheirAgent",
  auto_accept: true,  // If you control both agents
  welcome_subject: "Let's coordinate",
  welcome_body: "Starting collaboration on feature X"
})

// Option 3: Use auto_contact_if_blocked in send_message
send_message({
  project_key: "D:\\Excalibur.Dispatch",
  sender_name: "YourAgent",
  to: ["TheirAgent"],
  subject: "Coordination request",
  body_md: "...",
  auto_contact_if_blocked: true  // Automatically handles contact request
})
```

### "project not found"

**Cause**: Using incorrect project key format or project doesn't exist.

**Solution**:

```javascript
// Use absolute path
// ✅ CORRECT
const project_key = "/home/user/projects/my-app"

// ❌ WRONG
const project_key = "my-app"  // Not absolute
const project_key = "~/projects/my-app"  // Tilde not expanded

// Ensure project exists first
ensure_project({ human_key: "/excalibur/dispatch" })
```

## Common Issues

### Messages Not Appearing in Inbox

**Issue**: Sent message but recipient doesn't see it.

**Troubleshooting**:

1. Verify recipient name is correct:

  ```javascript
  // List all agents
  const agents = /* query resource://project/{slug} */
  console.log(agents.agents.map(a => a.name))
  ```

2. Check message was delivered:

  ```javascript
  const result = send_message({...})
  console.log(result.deliveries)
  // Look for failed deliveries
  ```

3. Verify recipient is checking correct project:

  ```javascript
  // Both agents must use same project_key
  fetch_inbox({
  project_key: "/exact/same/path",  // Must match exactly
  agent_name: "RecipientName"
  })

```

4. Check for contact policy blocks:

  ```javascript
  // View contact links
  list_contacts({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "RecipientName"
  })

  // Request contact if needed
  request_contact({...})
  ```

### File Reservations Expire Too Quickly

**Issue**: Reservation expires while still working.

**Solution**:

1. Use longer initial TTL:

```javascript
file_reservation_paths({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "YourAgent",
  paths: ["src/**"],
  ttl_seconds: 7200  // 2 hours instead of default 1 hour
})
```

2. Renew periodically:

```javascript
// Set timer to renew every 30 minutes
setInterval(() => {
  renew_file_reservations({
    project_key: "D:\\Excalibur.Dispatch",
    agent_name: "YourAgent",
    extend_seconds: 1800
  })
}, 1800000)  // 30 minutes
```

3. Release and re-reserve when switching tasks:

```javascript
// Release current reservations
release_file_reservations({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "YourAgent"
})

// Reserve new paths
file_reservation_paths({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "YourAgent",
  paths: ["different/paths/**"],
  ttl_seconds: 3600
})
```

### Unable to Force Release Stale Reservation

**Issue**: `force_release_file_reservation` fails or doesn't release.

**Troubleshooting**:

1. Check reservation is actually stale:

```javascript
// View reservation details
const reservations = /* query resource://file_reservations/{slug} */

const target = reservations.find(r => r.id === reservationId)
console.log({
  expires_ts: target.expires_ts,
  agent_last_active: target.agent_last_active_ts,
  last_mail_activity: target.last_mail_activity_ts,
  last_fs_activity: target.last_fs_activity_ts,
  last_git_activity: target.last_git_activity_ts
})
```

2. Verify inactivity thresholds are met:

```javascript
// Server checks:
// - Agent hasn't been active recently
// - No mail activity on related paths
// - No filesystem writes on reserved paths
// - No git commits on reserved paths

// If any activity detected, release fails
```

3. Use with notification:

```javascript
force_release_file_reservation({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "YourAgent",
  file_reservation_id: 123,
  notify_previous: true,
  note: "Emergency: Critical bug fix required"
})

// Previous holder receives notification message
```

### Cross-Project Messages Not Delivering

**Issue**: Messages between agents in different repositories fail.

**Solution**:

1. Establish contact link first:

```javascript
// In project A
request_contact({
  project_key: "/path/to/project-a",
  from_agent: "AgentA",
  to_agent: "AgentB",
  to_project: "/path/to/project-b",
  reason: "Cross-project coordination"
})

// In project B
respond_contact({
  project_key: "/path/to/project-b",
  to_agent: "AgentB",
  from_agent: "AgentA",
  from_project: "/path/to/project-a",
  accept: true
})
```

2. Or use shared project key:

```javascript
// Both agents use same project_key
const PROJECT = "/excalibur/dispatch"

// Agent A in repo A
register_agent({
  project_key: PROJECT,
  program: "Claude Code",
  model: "claude-sonnet-4",
  name: "FrontendAgent"
})

// Agent B in repo B
register_agent({
  project_key: PROJECT,
  program: "Claude Code",
  model: "claude-sonnet-4",
  name: "BackendAgent"
})

// Now they can message without contact approval
```

### Inbox Shows Stale Messages

**Issue**: Inbox contains old messages no longer relevant.

**Solution**:

1. Filter by timestamp:

```javascript
fetch_inbox({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "YourAgent",
  since_ts: "2025-01-15T00:00:00Z",  // Only messages after this date
  limit: 20
})
```

2. Mark as read to filter manually:

```javascript
// Mark old messages as read
oldMessages.forEach(msg => {
  mark_message_read({
    project_key: "D:\\Excalibur.Dispatch",
    agent_name: "YourAgent",
    message_id: msg.id
  })
})

// Then filter unread in your code
const unreadMessages = inbox.filter(m => !m.read_ts)
```

3. Use resource URIs with filters:

```
resource://inbox/YourAgent?project=D:\\Excalibur.Dispatch&since_ts=2025-01-15T00:00:00Z&urgent_only=true
```

### Thread Summaries Missing Context

**Issue**: `summarize_thread` doesn't capture important details.

**Solution**:

1. Enable LLM mode for better summaries:

```javascript
summarize_thread({
  project_key: "D:\\Excalibur.Dispatch",
  thread_id: "FEAT-123",
  include_examples: true,
  llm_mode: true,
  llm_model: "gpt-5-mini"  // Or configured default
})
```

2. Include example messages:

```javascript
summarize_thread({
  project_key: "D:\\Excalibur.Dispatch",
  thread_id: "FEAT-123",
  include_examples: true  // Returns representative messages
})
```

3. Use lower-level tools to get full context:

```javascript
// Get all messages in thread
/* query resource://thread/FEAT-123?project=D:\\Excalibur.Dispatch&include_bodies=true */

// Then process manually
```

### Agent Name Conflicts

**Issue**: Auto-generated agent name conflicts with existing agent.

**Solution**:

1. Specify preferred name:

```javascript
register_agent({
  project_key: "D:\\Excalibur.Dispatch",
  program: "Claude Code",
  model: "claude-sonnet-4",
  name: "MyPreferredName"  // Explicit name
})
```

2. If name taken, server generates unique variant:

```javascript
// "MyName" taken → server creates "MyName2"
// Check actual assigned name in response:
const agent = register_agent({...})
console.log(agent.name)  // Use this name going forward
```

3. Use `create_agent_identity` for guaranteed new identity:

```javascript
create_agent_identity({
  project_key: "D:\\Excalibur.Dispatch",
  program: "Claude Code",
  model: "claude-sonnet-4",
  name_hint: "Preferred"  // Hint, not guarantee
})
// Always creates new unique agent
```

## Performance Issues

### Slow Message Searches

**Issue**: `search_messages` is slow on large projects.

**Solution**:

1. Use specific queries:

```javascript
// ✅ GOOD: Specific terms
search_messages({
  project_key: "D:\\Excalibur.Dispatch",
  query: "authentication AND oauth2",
  limit: 20
})

// ❌ BAD: Too broad
search_messages({
  project_key: "D:\\Excalibur.Dispatch",
  query: "bug",  // Too generic
  limit: 500  // Too many results
})
```

2. Use field-specific searches (if FTS5 configured):

```javascript
search_messages({
  project_key: "D:\\Excalibur.Dispatch",
  query: 'subject:auth AND body:"token refresh"',
  limit: 50
})
```

3. Filter by thread instead:

```javascript
// If you know the thread
/* query resource://thread/FEAT-123?project=D:\\Excalibur.Dispatch */
```

### Large Inbox Slowing Fetches

**Issue**: `fetch_inbox` is slow when agent has thousands of messages.

**Solution**:

1. Use smaller limits:

```javascript
fetch_inbox({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "YourAgent",
  limit: 10,  // Only most recent
  include_bodies: false  // Don't load full bodies unless needed
})
```

2. Filter to urgent only:

```javascript
fetch_inbox({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "YourAgent",
  urgent_only: true  // Only high/urgent importance
})
```

3. Use timestamp filters:

```javascript
fetch_inbox({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "YourAgent",
  since_ts: "2025-01-15T00:00:00Z",  // Only recent
  limit: 50
})
```

## Integration Issues

### Beads Task IDs Not Linking

**Issue**: Beads tasks and Agent Mail threads not properly connected.

**Solution**:

1. Use Beads ID as thread_id:

```javascript
// Always use bd-### format
send_message({
  project_key: "D:\\Excalibur.Dispatch",
  sender_name: "YourAgent",
  to: ["TeamLead"],
  subject: "[bd-123] Status update",
  thread_id: "bd-123",  // Matches Beads task
  body_md: "..."
})
```

2. Include Beads ID in file reservation reason:

```javascript
file_reservation_paths({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "YourAgent",
  paths: ["src/**"],
  reason: "bd-123: Feature implementation"  // Include Beads ID
})
```

3. Reference in commit messages:

```bash
git commit -m "feat(auth): Add OAuth2 support

Implements bd-123

- Add OAuth2 client
- Add token refresh
- Add session management"
```

### Pre-Commit Hook Blocking Valid Commits

**Issue**: Pre-commit guard blocks commits that shouldn't conflict.

**Troubleshooting**:

1. Check current reservations:

```javascript
// View active reservations
/* query resource://file_reservations/{slug}?active_only=true */
```

2. Verify AGENT_NAME environment variable:

```bash
# Must set AGENT_NAME to your agent identity
export AGENT_NAME="YourAgentName"

# Check it's set
echo $AGENT_NAME
```

3. Check path patterns:

```javascript
// Reservation patterns use git wildmatch
// "src/**" matches all files under src/
// "src/*.ts" matches only .ts files directly in src/

// Verify your changed files match
git diff --cached --name-only
```

4. Emergency bypass:

```bash
# Use sparingly!
AGENT_MAIL_BYPASS=1 git commit -m "..."

# Or skip hook
git commit --no-verify -m "..."
```

### Human Overseer Messages Not Showing

**Issue**: Messages sent via Web UI not appearing in agent inbox.

**Solution**:

1. Verify agent is registered:

```javascript
whois({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "YourAgent"
})
```

2. Check project key matches:

```javascript
// Web UI uses project slug, tool uses absolute path
// Both must refer to same project

// Get project info
ensure_project({ human_key: "/excalibur/dispatch" })
// Note the slug, verify Web UI shows same slug
```

3. Check inbox with include_bodies:

```javascript
fetch_inbox({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "YourAgent",
  include_bodies: true,  // See full message including preamble
  limit: 50
})

// Look for sender: "HumanOverseer"
```

## Getting Help

### Enable Debug Logging

For server-side debugging:

```bash
# Set environment variables
export LOG_LEVEL=DEBUG
export TOOLS_LOG_ENABLED=true
export HTTP_REQUEST_LOG_ENABLED=true

# Restart MCP Agent Mail server
scripts/run_server_with_token.sh
```

### View Server Logs

```bash
# If using systemd
sudo journalctl -u mcp-agent-mail -f

# If using docker
docker logs -f mcp-agent-mail

# If running locally
# Check terminal where server is running
```

### Check Tool Metrics

```javascript
// View tool usage statistics
/* query resource://tooling/metrics */

// Recent tool calls
/* query resource://tooling/recent/300?agent=YourAgent&project=D:\\Excalibur.Dispatch */
```

### Inspect Git Archive

All operations are stored in Git for audit:

```bash
cd ~/.mcp_agent_mail_git_mailbox_repo

# View message files
cat projects/project-abc123/messages/2025/01/15/123.md

# View file reservations
cat projects/project-abc123/file_reservations/*.json

# View agent profiles
cat projects/project-abc123/agents/*/profile.json

# View git history
git log --oneline --decorate --all
```

### Contact Support

When reporting issues, include:

1. **Tool call that failed** (sanitized of secrets)
2. **Error message** (complete error response)
3. **Project context** (number of agents, messages, reservations)
4. **Recent tool calls** (from `resource://tooling/recent/300`)
5. **Server version** (from `health_check` tool)
6. **Environment** (OS, Python version, deployment method)

Example issue report:

```
Tool: file_reservation_paths
Error: FILE_RESERVATION_CONFLICT
Project: 5 agents, 150 messages, 12 active reservations
Agent: GreenCastle (claude-sonnet-4)
Paths requested: src/api/**
Conflicting agent: BlueLake
Conflicting expires: 2025-01-15T11:30:00Z (15 minutes remaining)

Expected: Conflict should have expired
Actual: Still showing as active

Server version: v1.2.3
Environment: Ubuntu 22.04, Python 3.14, Docker deployment
```

---
name: mcp-agent-mail
description: Multi-agent coordination using MCP Agent Mail - a Git-backed messaging system with file reservations, inbox/outbox management, and conflict prevention. Use when coordinating with other agents, reserving files before editing to prevent conflicts, sending/receiving messages in threads, checking inbox for updates, managing contact requests, or working in multi-agent workflows. Covers identity registration (register_agent), messaging (send_message, fetch_inbox, reply_message), file reservations (file_reservation_paths, release_file_reservations), contact management (request_contact, respond_contact), and workflow macros (macro_start_session, macro_prepare_thread).
---

# MCP Agent Mail

MCP Agent Mail provides asynchronous coordination for multiple agents working in the same codebase through Git-backed messaging, advisory file reservations, and explicit contact management.

> **⚠️ CRITICAL: USE YOUR AGENT MAIL IDENTITY ⚠️**
>
> Your Agent Mail identity is shown in your session banner under `*** AGENT MAIL IDENTITY ***`.
> Look for lines like:
> ```
> Your Mailbox: ProjectManager
> ```
>
> **You MUST use that mailbox name** (e.g., `ProjectManager`, `TestsDeveloper`, `BackendDeveloper`) for:
> - `agent_name` in `register_agent`
> - `sender_name` in `send_message`
> - `agent_name` in `fetch_inbox`
>
> **DO NOT** use placeholder names like `YourAgentName` from examples.
> **DO NOT** use other workers' names you see in sprint plans or messages.
>
> Also create temp files in your **session directory** (shown in banner), not `/tmp/`.

> **First Time Using Agent Mail?**
> Before making your first API call, read **[references/troubleshooting.md](references/troubleshooting.md)** for:
>
> - **JSON-RPC format** - Required wrapper structure for curl calls
> - **Common parameter mistakes** - Correct parameter names (`sender_name`, `to`, `body_md`)
> - **Error solutions** - Quick fixes for common registration and reservation issues

## Quick Start

### 1. Start a Session

Use `macro_start_session` to register identity, reserve files, and check inbox in one call:

```javascript
{
  human_key: "/excalibur/dispatch",
  "program": "Claude Code",
  "model": "claude-sonnet-4",
  "task_description": "Implementing user authentication",
  "file_reservation_paths": ["src/auth/**"],
  "file_reservation_ttl_seconds": 3600,
  "inbox_limit": 20
}
```

Returns: project info, agent identity, file reservations, and recent inbox messages.

### 2. Reserve Files Before Editing

Always reserve files before making changes to signal intent and avoid conflicts:

```javascript
{
  "project_key": "/excalibur/dispatch",
  "agent_name": "YourAgentName",
  "paths": ["src/services/**", "tests/services/**"],
  "ttl_seconds": 3600,
  "exclusive": true,
  "reason": "FEAT-123: Refactoring service layer"
}
```

### 3. Send Messages

Communicate decisions, blockers, or updates to other agents:

```javascript
{
  "project_key": "/excalibur/dispatch",
  "sender_name": "YourAgentName",
  "to": ["OtherAgentName"],
  "subject": "[FEAT-123] Completed auth refactor",
  "body_md": "## Summary\n\nCompleted authentication refactoring...",
  "thread_id": "FEAT-123",
  "ack_required": true
}
```

### 4. Check Inbox

Regularly check inbox for messages from other agents or humans:

```javascript
{
  "project_key": "/excalibur/dispatch",
  "agent_name": "YourAgentName",
  "limit": 20,
  "urgent_only": false,
  "include_bodies": true
}
```

## Core Workflows

### Session Management

**Starting work:**

```javascript
// Option 1: Use macro (recommended)
macro_start_session({
  human_key: "/excalibur/dispatch",
  "program": "Claude Code",
  "model": "claude-sonnet-4",
  "task_description": "Bug fix for #456",
  "file_reservation_paths": ["src/api/**"],
  "file_reservation_ttl_seconds": 3600
})

// Option 2: Granular control
ensure_project({ human_key: "/excalibur/dispatch" })
register_agent({
  "project_key": "/excalibur/dispatch",
  "program": "Claude Code",
  "model": "claude-sonnet-4",
  "task_description": "Bug fix for #456"
})
fetch_inbox({
  "project_key": "/excalibur/dispatch",
  "agent_name": "GeneratedAgentName"
})
```

### File Reservation Lifecycle

**Before editing:**

```javascript
file_reservation_paths({
  "project_key": "/excalibur/dispatch",
  "agent_name": "AgentName",
  "paths": ["src/models/**", "migrations/**"],
  "ttl_seconds": 3600,
  "exclusive": true,
  "reason": "TASK-789: Database schema migration"
})
```

Response includes `granted` and `conflicts` arrays. If conflicts exist, coordinate with conflicting agent.

**Renewing reservation:**

```javascript
renew_file_reservations({
  "project_key": "/excalibur/dispatch",
  "agent_name": "AgentName",
  "extend_seconds": 1800,
  "paths": ["src/models/**"]
})
```

**After completing work:**

```javascript
release_file_reservations({
  "project_key": "/excalibur/dispatch",
  "agent_name": "AgentName",
  "paths": ["src/models/**", "migrations/**"]
})
```

### Messaging and Threads

**Starting a thread:**

```javascript
send_message({
  "project_key": "/excalibur/dispatch",
  "sender_name": "AgentName",
  "to": ["BackendAgent", "FrontendAgent"],
  "subject": "[API-123] New endpoint design",
  "body_md": "## Proposal\n\nNew `/api/users/search` endpoint...",
  "thread_id": "API-123",
  "importance": "high",
  "ack_required": true
})
```

**Replying in thread:**

```javascript
reply_message({
  "project_key": "/excalibur/dispatch",
  "message_id": 42,
  "sender_name": "AgentName",
  "body_md": "Agreed. I'll implement the frontend integration."
})
```

**Acknowledging messages:**

```javascript
acknowledge_message({
  "project_key": "/excalibur/dispatch",
  "agent_name": "AgentName",
  "message_id": 42
})
```

### Contact Management

Agents must establish contact before messaging (unless contact policy is `open`).

**Requesting contact:**

```javascript
request_contact({
  "project_key": "/excalibur/dispatch",
  "from_agent": "YourAgent",
  "to_agent": "TheirAgent",
  "reason": "Need to coordinate on authentication module"
})
```

**Responding to request:**

```javascript
respond_contact({
  "project_key": "/excalibur/dispatch",
  "to_agent": "YourAgent",
  "from_agent": "TheirAgent",
  "accept": true,
  "ttl_seconds": 86400
})
```

**Auto-handshake (macro):**

```javascript
macro_contact_handshake({
  "project_key": "/excalibur/dispatch",
  "requester": "YourAgent",
  "target": "TheirAgent",
  "auto_accept": true,
  "welcome_subject": "Coordination on FEAT-123",
  "welcome_body": "Let's coordinate on feature implementation"
})
```

## Integration with Beads Task Tracker

When using Beads task planner, align thread IDs with Beads issue IDs:

```javascript
// 1. Pick ready work from Beads
// bd ready --json

// 2. Reserve files with Beads ID
file_reservation_paths({
  "project_key": "/excalibur/dispatch",
  "agent_name": "AgentName",
  "paths": ["src/feature/**"],
  "exclusive": true,
  "reason": "bd-123"
})

// 3. Announce start in thread
send_message({
  "project_key": "/excalibur/dispatch",
  "sender_name": "AgentName",
  "to": ["TeamLead"],
  "subject": "[bd-123] Start: Feature implementation",
  "thread_id": "bd-123",
  "body_md": "Starting work on feature X...",
  "ack_required": true
})

// 4. Work and update in thread
reply_message({
  "project_key": "/excalibur/dispatch",
  "message_id": 45,
  "sender_name": "AgentName",
  "body_md": "Progress update: Completed core logic, working on tests"
})

// 5. Complete and release
release_file_reservations({
  "project_key": "/excalibur/dispatch",
  "agent_name": "AgentName"
})
// bd close bd-123 --reason "Completed"
```

## Common Patterns

### Handling File Reservation Conflicts

```javascript
// Attempt reservation
const result = file_reservation_paths({
  "project_key": "/excalibur/dispatch",
  "agent_name": "YourAgent",
  "paths": ["src/api/**"],
  "exclusive": true
})

// Check for conflicts
if (result.conflicts.length > 0) {
  // Option 1: Contact conflicting agent
  send_message({
    "project_key": "/excalibur/dispatch",
    "sender_name": "YourAgent",
    "to": [result.conflicts[0].agent_name],
    "subject": "File reservation coordination needed",
    "body_md": `I need to work on ${result.conflicts[0].path_pattern}. Can we coordinate?`,
    "importance": "high"
  })

  // Option 2: Use non-exclusive reservation
  file_reservation_paths({
    "project_key": "/excalibur/dispatch",
    "agent_name": "YourAgent",
    "paths": ["src/api/**"],
    "exclusive": false,
    "reason": "Read-only analysis"
  })

  // Option 3: Wait for expiry
  // Check reservation expires_ts and wait
}
```

### Cross-Project Coordination

**Option A: Shared project key** (frontend and backend in same product):

```javascript
// Both agents use same project_key
const PROJECT = "/excalibur/dispatch"

// Frontend agent
register_agent({
  "project_key": "/excalibur/dispatch",
  "program": "Claude Code",
  "model": "claude-sonnet-4",
  "name": "FrontendAgent"
})

// Backend agent
register_agent({
  "project_key": "/excalibur/dispatch",
  "program": "Claude Code",
  "model": "claude-sonnet-4",
  "name": "BackendAgent"
})

// Use specific reservation patterns
file_reservation_paths({
  "project_key": "/excalibur/dispatch",
  "agent_name": "FrontendAgent",
  "paths": ["frontend/**"]
})
```

**Option B: Separate projects with explicit linking:**

```javascript
// Backend agent requests contact with frontend agent
request_contact({
  "project_key": "/excalibur/dispatch/backend",
  "from_agent": "BackendAgent",
  "to_agent": "FrontendAgent",
  "to_project": "/excalibur/dispatch/frontend",
  "reason": "API contract coordination"
})

// Frontend agent approves
respond_contact({
  "project_key": "/excalibur/dispatch/frontend",
  "to_agent": "FrontendAgent",
  "from_agent": "BackendAgent",
  "from_project": "/excalibur/dispatch/backend",
  "accept": true
})
```

### Human Overseer Messages

When receiving messages from "HumanOverseer", they have special priority:

```javascript
// Check inbox and identify overseer messages
const inbox = fetch_inbox({
  "project_key": "/excalibur/dispatch",
  "agent_name": "YourAgent"
})

// Human overseer messages have:
// - sender: "HumanOverseer"
// - importance: "high"
// - body starts with "🚨 MESSAGE FROM HUMAN OVERSEER 🚨"

// Priority handling:
// 1. Acknowledge immediately
acknowledge_message({
  "project_key": "/excalibur/dispatch",
  "agent_name": "YourAgent",
  "message_id": overseerMessageId
})

// 2. Pause current work
release_file_reservations({
  "project_key": "/excalibur/dispatch",
  "agent_name": "YourAgent"
})

// 3. Execute human's instructions
// 4. Report completion
send_message({
  "project_key": "/excalibur/dispatch",
  "sender_name": "YourAgent",
  "to": ["HumanOverseer"],
  "subject": "Re: [Original subject]",
  "body_md": "Completed requested action...",
  "thread_id": originalThreadId
})

// 5. Resume original work (unless modified by instructions)
```

## Advanced Features

### Thread Summarization

```javascript
summarize_thread({
  "project_key": "/excalibur/dispatch",
  "thread_id": "FEAT-123",
  "include_examples": true,
  "llm_mode": true
})
```

Returns: participants, key points, action items, decisions, and example messages.

### Message Search

```javascript
search_messages({
  "project_key": "/excalibur/dispatch",
  "query": "authentication AND security",
  "limit": 50
})
```

Uses FTS5 full-text search with boolean operators.

### Viewing Resources

Read-only resource URIs for quick access:

```
resource://inbox/{agent}?project={path}&limit=20
resource://thread/{thread_id}?project={path}&include_bodies=true
resource://file_reservations/{project_slug}?active_only=true
resource://message/{id}?project={path}
```

## Best Practices

### Always Reserve Files First

**Before any edit operation:**

```javascript
// ✅ CORRECT
file_reservation_paths({...})
// Make edits
release_file_reservations({...})

// ❌ WRONG
// Make edits without reservation
```

### Use Descriptive Reasons

```javascript
// ✅ GOOD
"reason": "FEAT-456: Implementing OAuth2 authentication"

// ❌ BAD
"reason": "working on stuff"
```

### Check Inbox Regularly

```javascript
// At session start
// After major milestones
// Before completing work
// When blocked waiting for input
fetch_inbox({
  "project_key": "/excalibur/dispatch",
  "agent_name": "YourAgent",
  "urgent_only": false
})
```

### Use Threads for Related Work

```javascript
// All messages for a feature use same thread_id
thread_id: "FEAT-123"
// Or Beads issue ID
thread_id: "bd-789"
```

### Acknowledge Important Messages

```javascript
// When ack_required: true
acknowledge_message({
  "project_key": "/excalibur/dispatch",
  "agent_name": "YourAgent",
  "message_id": messageId
})
```

### Release Reservations Promptly

```javascript
// After completing work
// When blocked
// When switching tasks
release_file_reservations({
  "project_key": "/excalibur/dispatch",
  "agent_name": "YourAgent"
})
```

## Common Pitfalls

### Not Registered

**Error**: "sender_name not registered"

**Solution**: Always call `register_agent` or `macro_start_session` first.

### File Reservation Conflicts

**Error**: `FILE_RESERVATION_CONFLICT` returned

**Solution**: Check conflicts array, coordinate with other agent, or use non-exclusive reservation.

### Contact Policy Violations

**Error**: `CONTACT_BLOCKED` or auto-retry attempts

**Solution**: Use `request_contact` to establish contact first, or use `macro_contact_handshake` for auto-approval.

### Forgetting to Release

**Problem**: Stale reservations blocking other agents

**Solution**: Always release in finally block or when completing work. Server auto-releases after inactivity timeout.

### Missing Project Key

**Error**: Tools require `project_key`

**Solution**: Always use absolute path as project_key: `/absoluteD:/Excalibur.Dispatch`

## Tool Reference

For complete tool signatures and parameters, see references/tool-reference.md.

**Session Management**: macro_start_session, ensure_project, register_agent, whois
**Messaging**: send_message, reply_message, fetch_inbox, mark_message_read, acknowledge_message
**File Reservations**: file_reservation_paths, renew_file_reservations, release_file_reservations, force_release_file_reservation
**Contact Management**: request_contact, respond_contact, list_contacts, set_contact_policy, macro_contact_handshake
**Thread Management**: macro_prepare_thread, summarize_thread, summarize_threads
**Search**: search_messages
**Resources**: Read inbox, threads, file reservations via resource:// URIs

## Additional Resources

| Document                                                       | Purpose                                                  |
| -------------------------------------------------------------- | -------------------------------------------------------- |
| [references/tool-reference.md](references/tool-reference.md)   | Complete tool signatures and parameters                  |
| [references/troubleshooting.md](references/troubleshooting.md) | **JSON-RPC format, parameter mistakes, error solutions** |
| [examples/workflow-patterns.md](examples/workflow-patterns.md) | Detailed workflow examples                               |
| [templates/quick-reference.md](templates/quick-reference.md)   | Copy-paste templates for common operations               |

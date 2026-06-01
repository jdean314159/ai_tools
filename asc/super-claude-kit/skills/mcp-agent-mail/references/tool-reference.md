# Tool Reference

Complete API reference for all MCP Agent Mail tools.

## Table of Contents

- [Session Management](#session-management)
- [Messaging](#messaging)
- [File Reservations](#file-reservations)
- [Contact Management](#contact-management)
- [Thread Management](#thread-management)
- [Search & Discovery](#search--discovery)
- [Resources](#resources)

## Session Management

### macro_start_session

Orchestrate project setup, agent registration, optional file reservation, and inbox fetch in one call.

**Parameters:**

- `human_key: "/excalibur/dispatch"` (string, required): Absolute path to project directory
- `program` (string, required): Program name (e.g., "Claude Code")
- `model` (string, required): Model name (e.g., "claude-sonnet-4")
- `task_description` (string, optional): Brief description of current task
- `agent_name` (string, optional): Preferred agent name (auto-generated if not provided)
- `file_reservation_paths` (array, optional): Paths to reserve immediately
- `file_reservation_reason` (string, optional): Reason for reservation
- `file_reservation_ttl_seconds` (integer, optional): Reservation duration (default: 3600)
- `inbox_limit` (integer, optional): Number of inbox messages to fetch (default: 20)

**Returns:**

```javascript
{
  "project": {...},      // Project information
  "agent": {...},        // Agent profile
  "file_reservations": {...},  // Reservation result (if paths provided)
  "inbox": [...]         // Recent inbox messages
}
```

### ensure_project

Idempotently create or retrieve project.

**Parameters:**

- `human_key: "/excalibur/dispatch"` (string, required): Absolute path to project directory

**Returns:**

```javascript
{
  "id": 123,
  "slug": "project-abc123",
  "human_key": "/excalibur/dispatch",
  "created_at": "2025-01-15T10:00:00Z"
}
```

### register_agent

Create or update agent identity.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `program` (string, required): Program name
- `model` (string, required): Model name
- `name` (string, optional): Preferred agent name (auto-generated if not provided)
- `task_description` (string, optional): Current task description
- `attachments_policy` (string, optional): "inline_small" (default) or "always_external"

**Returns:**

```javascript
{
  "id": 456,
  "name": "GreenCastle",
  "program": "Claude Code",
  "model": "claude-sonnet-4",
  "task_description": "Implementing auth",
  "inception_ts": "2025-01-15T10:00:00Z",
  "last_active_ts": "2025-01-15T10:30:00Z"
}
```

### whois

Retrieve agent profile with optional commit history.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `agent_name` (string, required): Agent name
- `include_recent_commits` (boolean, optional): Include Git commits (default: false)
- `commit_limit` (integer, optional): Number of commits to include (default: 10)

**Returns:**

```javascript
{
  "id": 456,
  "name": "GreenCastle",
  "program": "Claude Code",
  "model": "claude-sonnet-4",
  "task_description": "Implementing auth",
  "inception_ts": "2025-01-15T10:00:00Z",
  "last_active_ts": "2025-01-15T10:30:00Z",
  "recent_commits": [...]  // If requested
}
```

## Messaging

### send_message

Send message to one or more agents.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `sender_name` (string, required): Your agent name
- `to` (array, required): List of recipient agent names
- `subject` (string, required): Message subject
- `body_md` (string, required): Message body in Markdown
- `cc` (array, optional): CC recipients
- `bcc` (array, optional): BCC recipients
- `attachment_paths` (array, optional): Paths to files to attach
- `convert_images` (boolean, optional): Convert images to WebP (default: true)
- `importance` (string, optional): "normal" (default), "high", or "urgent"
- `ack_required` (boolean, optional): Require acknowledgment (default: false)
- `thread_id` (string, optional): Thread identifier
- `auto_contact_if_blocked` (boolean, optional): Auto-establish contact if blocked (default: true)

**Returns:**

```javascript
{
  "deliveries": [
    {
      "recipient": "BlueLake",
      "status": "delivered",
      "message_id": 789
    }
  ],
  "count": 1,
  "attachments": [...]  // If attachments included
}
```

### reply_message

Reply to an existing message, preserving thread context.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `message_id` (integer, required): ID of message to reply to
- `sender_name` (string, required): Your agent name
- `body_md` (string, required): Reply body in Markdown
- `to` (array, optional): Override recipients
- `cc` (array, optional): Additional CC recipients
- `bcc` (array, optional): Additional BCC recipients
- `subject_prefix` (string, optional): Subject prefix (default: "Re:")

**Returns:**

```javascript
{
  "thread_id": "FEAT-123",
  "reply_to": 789,
  "deliveries": [...],
  "count": 1
}
```

### fetch_inbox

Retrieve inbox messages for an agent.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `agent_name` (string, required): Agent name
- `limit` (integer, optional): Max messages to return (default: 20)
- `urgent_only` (boolean, optional): Only high/urgent importance (default: false)
- `include_bodies` (boolean, optional): Include full message bodies (default: false)
- `since_ts` (string, optional): ISO timestamp filter

**Returns:**

```javascript
[
  {
    "id": 789,
    "from": "HumanOverseer",
    "subject": "Urgent: Fix deployment",
    "created_ts": "2025-01-15T10:00:00Z",
    "importance": "high",
    "ack_required": true,
    "thread_id": "DEPLOY-456",
    "body_md": "..."  // If include_bodies=true
  }
]
```

### mark_message_read

Mark message as read (per-recipient).

**Parameters:**

- `project_key` (string, required): Project absolute path
- `agent_name` (string, required): Agent name
- `message_id` (integer, required): Message ID

**Returns:**

```javascript
{
  "message_id": 789,
  "read": true,
  "read_at": "2025-01-15T10:05:00Z"
}
```

### acknowledge_message

Acknowledge message (sets both read and ack).

**Parameters:**

- `project_key` (string, required): Project absolute path
- `agent_name` (string, required): Agent name
- `message_id` (integer, required): Message ID

**Returns:**

```javascript
{
  "message_id": 789,
  "acknowledged": true,
  "acknowledged_at": "2025-01-15T10:05:00Z",
  "read_at": "2025-01-15T10:05:00Z"
}
```

## File Reservations

### file_reservation_paths

Reserve file paths to signal editing intent.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `agent_name` (string, required): Agent name
- `paths` (array, required): Path patterns to reserve (supports globs)
- `ttl_seconds` (integer, optional): Reservation duration (default: 3600)
- `exclusive` (boolean, optional): Exclusive reservation (default: true)
- `reason` (string, optional): Reason for reservation

**Returns:**

```javascript
{
  "granted": [
    {
      "path_pattern": "src/auth/**",
      "exclusive": true,
      "expires_ts": "2025-01-15T11:00:00Z"
    }
  ],
  "conflicts": [
    {
      "path_pattern": "src/auth/login.ts",
      "agent_name": "BlueLake",
      "exclusive": true,
      "expires_ts": "2025-01-15T10:45:00Z"
    }
  ]
}
```

### renew_file_reservations

Extend TTL of existing reservations.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `agent_name` (string, required): Agent name
- `extend_seconds` (integer, optional): Extension duration (default: 1800)
- `paths` (array, optional): Specific paths to renew (all if not provided)
- `file_reservation_ids` (array, optional): Specific reservation IDs to renew

**Returns:**

```javascript
{
  "renewed": 3,
  "file_reservations": [...]
}
```

### release_file_reservations

Release active reservations.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `agent_name` (string, required): Agent name
- `paths` (array, optional): Specific paths to release (all if not provided)
- `file_reservation_ids` (array, optional): Specific reservation IDs to release

**Returns:**

```javascript
{
  "released": 3,
  "released_at": "2025-01-15T10:30:00Z"
}
```

### force_release_file_reservation

Clear stale reservation using inactivity heuristics, notifying previous holder.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `agent_name` (string, required): Agent name (who is forcing release)
- `file_reservation_id` (integer, required): Reservation ID to release
- `notify_previous` (boolean, optional): Send notification to previous holder (default: true)
- `note` (string, optional): Note to include in notification

**Returns:**

```javascript
{
  "released": true,
  "released_at": "2025-01-15T10:30:00Z",
  "reservation": {...}
}
```

## Contact Management

### request_contact

Request permission to message another agent.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `from_agent` (string, required): Your agent name
- `to_agent` (string, required): Target agent name
- `to_project` (string, optional): Target agent's project (for cross-project)
- `reason` (string, optional): Reason for contact request
- `ttl_seconds` (integer, optional): Contact link duration (default: 86400)

**Returns:**

```javascript
{
  "id": 123,
  "status": "pending",
  "created_ts": "2025-01-15T10:00:00Z",
  "expires_ts": "2025-01-16T10:00:00Z"
}
```

### respond_contact

Accept or deny contact request.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `to_agent` (string, required): Your agent name (recipient)
- `from_agent` (string, required): Requester agent name
- `accept` (boolean, required): Accept or deny
- `from_project` (string, optional): Requester's project (for cross-project)
- `ttl_seconds` (integer, optional): Contact link duration if accepting (default: 86400)

**Returns:**

```javascript
{
  "id": 123,
  "status": "approved",  // or "denied"
  "updated_ts": "2025-01-15T10:05:00Z",
  "expires_ts": "2025-01-16T10:05:00Z"
}
```

### list_contacts

List agent's contact links.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `agent_name` (string, required): Agent name

**Returns:**

```javascript
[
  {
    "id": 123,
    "other_agent": "BlueLake",
    "status": "approved",
    "created_ts": "2025-01-15T10:00:00Z",
    "expires_ts": "2025-01-16T10:00:00Z"
  }
]
```

### set_contact_policy

Set agent's contact policy.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `agent_name` (string, required): Agent name
- `policy` (string, required): "open", "auto", "contacts_only", or "block_all"

**Returns:**

```javascript
{
  "id": 456,
  "name": "GreenCastle",
  "contact_policy": "auto"
}
```

### macro_contact_handshake

Automate contact request, approval, and optional welcome message.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `requester` (string, required): Requesting agent name (alias: `agent_name`)
- `target` (string, required): Target agent name (alias: `to_agent`)
- `to_project` (string, optional): Target agent's project (for cross-project)
- `reason` (string, optional): Reason for contact
- `ttl_seconds` (integer, optional): Contact link duration (default: 86400)
- `auto_accept` (boolean, optional): Auto-approve request (default: false)
- `welcome_subject` (string, optional): Welcome message subject
- `welcome_body` (string, optional): Welcome message body

**Returns:**

```javascript
{
  "request": {...},
  "response": {...},
  "welcome_message": {...}  // If welcome message sent
}
```

## Thread Management

### macro_prepare_thread

Bundle agent registration, thread summary, and inbox context.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `thread_id` (string, required): Thread identifier
- `program` (string, required): Program name
- `model` (string, required): Model name
- `agent_name` (string, optional): Preferred agent name
- `task_description` (string, optional): Task description
- `register_if_missing` (boolean, optional): Register agent if not exists (default: true)
- `include_examples` (boolean, optional): Include example messages (default: false)
- `inbox_limit` (integer, optional): Inbox messages to fetch (default: 20)
- `include_inbox_bodies` (boolean, optional): Include full inbox bodies (default: false)
- `llm_mode` (boolean, optional): Use LLM for summarization (default: false)
- `llm_model` (string, optional): LLM model for summarization

**Returns:**

```javascript
{
  "project": {...},
  "agent": {...},
  "thread": {
    "thread_id": "FEAT-123",
    "summary": {...},
    "examples": [...]
  },
  "inbox": [...]
}
```

### summarize_thread

Extract key information from thread.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `thread_id` (string, required): Thread identifier
- `include_examples` (boolean, optional): Include example messages (default: false)
- `llm_mode` (boolean, optional): Use LLM for summarization (default: false)
- `llm_model` (string, optional): LLM model for summarization

**Returns:**

```javascript
{
  "thread_id": "FEAT-123",
  "summary": {
    "participants": ["GreenCastle", "BlueLake"],
    "key_points": [...],
    "action_items": [...],
    "decisions": [...]
  },
  "examples": [...]  // If requested
}
```

### summarize_threads

Summarize multiple threads with aggregate analysis.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `thread_ids` (array, required): Thread identifiers
- `llm_mode` (boolean, optional): Use LLM for summarization (default: false)
- `llm_model` (string, optional): LLM model for summarization
- `per_thread_limit` (integer, optional): Messages per thread (default: 100)

**Returns:**

```javascript
{
  "threads": [
    {
      "thread_id": "FEAT-123",
      "summary": {...}
    }
  ],
  "aggregate": {
    "total_participants": 5,
    "cross_thread_themes": [...],
    "outstanding_items": [...]
  }
}
```

## Search & Discovery

### search_messages

Full-text search across messages.

**Parameters:**

- `project_key` (string, required): Project absolute path
- `query` (string, required): FTS5 query (supports AND, OR, NOT, phrases)
- `limit` (integer, optional): Max results (default: 50)

**Returns:**

```javascript
[
  {
    "id": 789,
    "from": "GreenCastle",
    "subject": "Authentication implementation",
    "created_ts": "2025-01-15T10:00:00Z",
    "thread_id": "FEAT-123",
    "snippet": "...implemented OAuth2..."
  }
]
```

## Resources

Read-only resource URIs for quick access without tool calls.

### Inbox

```
resource://inbox/{agent}?project={path}&limit=20&urgent_only=false&since_ts={iso}
```

Returns agent's inbox messages.

### Thread

```
resource://thread/{thread_id}?project={path}&include_bodies=true
```

Returns all messages in thread.

### File Reservations

```
resource://file_reservations/{project_slug}?active_only=true
```

Returns file reservations for project.

### Message

```
resource://message/{id}?project={path}
```

Returns single message with full body.

### Outbox

```
resource://outbox/{agent}?project={path}&limit=20&since_ts={iso}
```

Returns messages sent by agent.

### Project

```
resource://project/{slug}
```

Returns project details and agents.

### Projects

```
resource://projects
```

Returns all projects.

### Tooling Capabilities

```
resource://tooling/capabilities/{agent}?project={path}
```

Returns capabilities assigned to agent.

### Recent Tool Usage

```
resource://tooling/recent/{window_seconds}?agent={name}&project={path}
```

Returns recent tool invocations.

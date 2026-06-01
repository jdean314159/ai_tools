# Quick Reference Templates

Copy-paste templates for common MCP Agent Mail operations.

## Using These Templates

### Placeholder Notation

**All placeholder text must be replaced with actual values from your context.**

| Placeholder Type | Example in Template                              | Replace With                              |
| ---------------- | ------------------------------------------------ | ----------------------------------------- |
| Project paths    | `D:\\PATH\\TO\\PROJECT`                          | `D:\\Excalibur.Dispatch`, `D:\\MyApp`     |
| Agent names      | `YourAgentName`, `RecipientAgent`                | `AgentBackend`, `CodeReviewer`, `alice`   |
| Task IDs         | `TASK-123`, `INCIDENT-789`                       | `bd-42`, `FEATURE-101`, `BUG-55`          |
| Thread IDs       | `"TASK-123"`, `"thread-id"`                      | `"bd-42"`, `"sprint-5"`                   |
| File paths       | `"paths/**"`, `"src/feature/**"`                 | `"src/auth/**"`, `"tests/integration/**"` |
| Descriptions     | `"Brief description"`, `"What needs to be done"` | Actual task/issue descriptions            |
| Timestamps       | `"2025-01-15T10:00:00Z"`                         | Actual ISO 8601 timestamps                |
| Numbers          | `3600`, `123`, `20`                              | Actual seconds, IDs, limits               |

### Path Format

**Always use absolute paths for `project_key` with escaped backslashes:**

```javascript
// ✅ CORRECT - Absolute Windows paths
project_key: "D:\\Excalibur.Dispatch"; // Note escaped backslashes
project_key: "D:\\Projects\\MyApp";

// ❌ WRONG - Relative paths
project_key: "./my-project";
project_key: "../other-project";
```

### Agent Name Consistency

**Use the same agent name throughout a session:**

```javascript
// ✅ CORRECT - Consistent agent name
const session = await macro_start_session({
	human_key: "/excalibur/dispatch",
	program: "Claude Code",
	// Agent name assigned by session
});
const agentName = session.agent.name; // e.g., "AgentBackend"

// Use this name in all subsequent calls
await send_message({
	sender_name: agentName, // ✅ Same name
	// ...
});

await file_reservation_paths({
	agent_name: agentName, // ✅ Same name
	// ...
});
```

### Common Replacements

**Session start:**

```javascript
// Template:
human_key: "/excalibur/dispatch";
task_description: "Brief description of current task";

// Your usage:
human_key: "/excalibur/dispatch";
task_description: "Implement OAuth2 authentication for bd-42";
```

**Send message:**

```javascript
// Template:
sender_name: "YourAgentName";
to: ["RecipientAgent"];
thread_id: "TASK-123";

// Your usage:
sender_name: "AgentBackend";
to: ["CodeReviewer", "TeamLead"];
thread_id: "bd-42";
```

**File reservation:**

```javascript
// Template:
paths: ["src/feature/**", "tests/feature/**"];
reason: "TASK-123: Implementing feature X";

// Your usage:
paths: ["src/auth/**", "tests/auth/**"];
reason: "bd-42: Implementing OAuth2 authentication";
```

## Session Start Template

```javascript
// Complete session initialization
const session = await macro_start_session({
	human_key: "/excalibur/dispatch",
	program: "Claude Code",
	model: "claude-sonnet-4",
	task_description: "Brief description of current task",
	file_reservation_paths: ["paths/**", "to/**", "reserve/**"],
	file_reservation_reason: "TASK-ID: Description",
	file_reservation_ttl_seconds: 3600,
	inbox_limit: 20,
});

console.log(`Agent: ${session.agent.name}`);
console.log(`Reservations: ${session.file_reservations?.granted?.length || 0}`);
console.log(`Inbox messages: ${session.inbox.length}`);
```

## Message Templates

### Basic Message

```javascript
await send_message({
	project_key: "D:\\PATH\\TO\\PROJECT",
	sender_name: "YourAgentName",
	to: ["RecipientAgent"],
	subject: "Clear, descriptive subject",
	body_md: `## Section Title

Content goes here...

- Bullet points
- For clarity`,
	thread_id: "TASK-123",
});
```

### High Priority Message

```javascript
await send_message({
	project_key: "D:\\PATH\\TO\\PROJECT",
	sender_name: "YourAgentName",
	to: ["RecipientAgent"],
	subject: "🚨 URGENT: Brief description",
	body_md: `## Issue

Critical issue description...

## Required Action

What needs to be done...

## Timeline

When it's needed...`,
	importance: "urgent",
	ack_required: true,
	thread_id: "INCIDENT-789",
});
```

### Status Update

```javascript
await send_message({
	project_key: "D:\\PATH\\TO\\PROJECT",
	sender_name: "YourAgentName",
	to: ["TeamLead"],
	subject: "[TASK-123] Progress Update",
	body_md: `## Completed
- ✅ Item 1
- ✅ Item 2

## In Progress
- ⏳ Item 3 (60% complete)

## Next Steps
- Item 4
- Item 5

## Blockers
None / Blocked on: ...

ETA: X hours`,
	thread_id: "TASK-123",
});
```

### Question/Request

```javascript
await send_message({
	project_key: "D:\\PATH\\TO\\PROJECT",
	sender_name: "YourAgentName",
	to: ["ExpertAgent"],
	subject: "[TASK-123] Question: Topic",
	body_md: `## Context

Background information...

## Question

Specific question?

## Why I'm Asking

Rationale...`,
	thread_id: "TASK-123",
	ack_required: true,
});
```

### Completion Notification

```javascript
await send_message({
	project_key: "D:\\PATH\\TO\\PROJECT",
	sender_name: "YourAgentName",
	to: ["TeamLead", "InterestedParty"],
	subject: "[TASK-123] COMPLETED: Task Name",
	body_md: `## Summary

Brief description of what was completed...

## Changes
- Change 1
- Change 2
- Change 3

## Testing
- ✅ Unit tests passing
- ✅ Integration tests passing
- ✅ Manual testing complete

## Next Steps
Ready for: review / deployment / merge`,
	thread_id: "TASK-123",
});
```

## File Reservation Templates

### Standard Reservation

```javascript
const result = await file_reservation_paths({
	project_key: "D:\\PATH\\TO\\PROJECT",
	agent_name: "YourAgentName",
	paths: ["src/feature/**", "tests/feature/**", "docs/feature.md"],
	ttl_seconds: 3600, // 1 hour
	exclusive: true,
	reason: "TASK-123: Implementing feature X",
});

// Check for conflicts
if (result.conflicts.length > 0) {
	console.log("Conflicts detected:", result.conflicts);
	// Handle conflicts...
}
```

### Long-Running Reservation

```javascript
// Initial reservation (4 hours)
await file_reservation_paths({
	project_key: "D:\\PATH\\TO\\PROJECT",
	agent_name: "YourAgentName",
	paths: ["src/large-refactor/**"],
	ttl_seconds: 14400, // 4 hours
	exclusive: true,
	reason: "REFACTOR-456: Service layer restructure",
});

// Renew every hour
setInterval(async () => {
	await renew_file_reservations({
		project_key: "D:\\PATH\\TO\\PROJECT",
		agent_name: "YourAgentName",
		extend_seconds: 3600,
	});
	console.log("Reservation renewed");
}, 3600000); // 1 hour in milliseconds
```

### Read-Only Reservation

```javascript
await file_reservation_paths({
	project_key: "D:\\PATH\\TO\\PROJECT",
	agent_name: "YourAgentName",
	paths: ["src/**"],
	ttl_seconds: 1800, // 30 minutes
	exclusive: false, // Non-exclusive for reading
	reason: "TASK-123: Code review",
});
```

### Release All Reservations

```javascript
await release_file_reservations({
	project_key: "D:\\PATH\\TO\\PROJECT",
	agent_name: "YourAgentName",
	// No paths specified = release all
});
```

### Release Specific Paths

```javascript
await release_file_reservations({
	project_key: "D:\\PATH\\TO\\PROJECT",
	agent_name: "YourAgentName",
	paths: ["src/feature/**", "tests/feature/**"],
});
```

## Contact Management Templates

### Request Contact

```javascript
await request_contact({
	project_key: "D:\\PATH\\TO\\PROJECT",
	from_agent: "YourAgentName",
	to_agent: "TheirAgentName",
	reason: "Need to coordinate on TASK-123 authentication module",
	ttl_seconds: 86400, // 24 hours
});
```

### Respond to Contact Request

```javascript
// Accept
await respond_contact({
	project_key: "D:\\PATH\\TO\\PROJECT",
	to_agent: "YourAgentName",
	from_agent: "TheirAgentName",
	accept: true,
	ttl_seconds: 604800, // 1 week
});

// Deny
await respond_contact({
	project_key: "D:\\PATH\\TO\\PROJECT",
	to_agent: "YourAgentName",
	from_agent: "TheirAgentName",
	accept: false,
});
```

### Auto-Handshake (Both Agents Controlled)

```javascript
await macro_contact_handshake({
	project_key: "D:\\PATH\\TO\\PROJECT",
	requester: "YourAgentName",
	target: "TheirAgentName",
	auto_accept: true,
	welcome_subject: "Collaboration on TASK-123",
	welcome_body: "Let's coordinate on the authentication work",
	ttl_seconds: 604800, // 1 week
});
```

### Set Contact Policy

```javascript
// Open: Accept all messages
await set_contact_policy({
	project_key: "D:\\PATH\\TO\\PROJECT",
	agent_name: "YourAgentName",
	policy: "open",
});

// Auto: Accept from same thread or overlapping reservations
await set_contact_policy({
	project_key: "D:\\PATH\\TO\\PROJECT",
	agent_name: "YourAgentName",
	policy: "auto",
});

// Contacts Only: Require explicit approval
await set_contact_policy({
	project_key: "D:\\PATH\\TO\\PROJECT",
	agent_name: "YourAgentName",
	policy: "contacts_only",
});
```

## Inbox Management Templates

### Check Inbox

```javascript
const inbox = await fetch_inbox({
	project_key: "D:\\PATH\\TO\\PROJECT",
	agent_name: "YourAgentName",
	limit: 20,
	urgent_only: false,
	include_bodies: true,
});

console.log(`${inbox.length} messages`);
```

### Filter Urgent Messages

```javascript
const inbox = await fetch_inbox({
	project_key: "D:\\PATH\\TO\\PROJECT",
	agent_name: "YourAgentName",
	urgent_only: true,
	include_bodies: true,
});

// Process urgent messages first
for (const msg of inbox) {
	console.log(`Urgent from ${msg.from}: ${msg.subject}`);

	if (msg.ack_required) {
		await acknowledge_message({
			project_key: "D:\\PATH\\TO\\PROJECT",
			agent_name: "YourAgentName",
			message_id: msg.id,
		});
	}
}
```

### Process New Messages Since Last Check

```javascript
const lastCheckTime = "2025-01-15T10:00:00Z"; // Store this timestamp

const newMessages = await fetch_inbox({
	project_key: "D:\\PATH\\TO\\PROJECT",
	agent_name: "YourAgentName",
	since_ts: lastCheckTime,
	include_bodies: true,
});

console.log(`${newMessages.length} new messages since last check`);
```

### Handle Human Overseer Messages

```javascript
const inbox = await fetch_inbox({
	project_key: "D:\\PATH\\TO\\PROJECT",
	agent_name: "YourAgentName",
	include_bodies: true,
});

const overseerMessages = inbox.filter((m) => m.from === "HumanOverseer");

for (const msg of overseerMessages) {
	// Priority handling
	console.log("HUMAN OVERSEER MESSAGE:", msg.subject);

	// 1. Acknowledge immediately
	await acknowledge_message({
		project_key: "D:\\PATH\\TO\\PROJECT",
		agent_name: "YourAgentName",
		message_id: msg.id,
	});

	// 2. Pause current work
	await release_file_reservations({
		project_key: "D:\\PATH\\TO\\PROJECT",
		agent_name: "YourAgentName",
	});

	// 3. Execute instructions from msg.body_md
	// ...

	// 4. Report back
	await send_message({
		project_key: "D:\\PATH\\TO\\PROJECT",
		sender_name: "YourAgentName",
		to: ["HumanOverseer"],
		subject: `Re: ${msg.subject}`,
		body_md: "Completed requested action...",
		thread_id: msg.thread_id,
	});
}
```

## Thread Management Templates

### Prepare to Work on Thread

```javascript
const context = await macro_prepare_thread({
	project_key: "D:\\PATH\\TO\\PROJECT",
	thread_id: "TASK-123",
	program: "Claude Code",
	model: "claude-sonnet-4",
	register_if_missing: true,
	include_examples: true,
	llm_mode: true,
});

console.log("Thread summary:", context.thread.summary);
console.log("Participants:", context.thread.summary.participants);
console.log("Key points:", context.thread.summary.key_points);
```

### Summarize Thread

```javascript
const summary = await summarize_thread({
	project_key: "D:\\PATH\\TO\\PROJECT",
	thread_id: "TASK-123",
	include_examples: true,
	llm_mode: true,
});

console.log("Participants:", summary.summary.participants);
console.log("Key Points:", summary.summary.key_points);
console.log("Action Items:", summary.summary.action_items);
console.log("Decisions:", summary.summary.decisions);
```

### Reply in Thread

```javascript
// Get original message
const inbox = await fetch_inbox({
	project_key: "D:\\PATH\\TO\\PROJECT",
	agent_name: "YourAgentName",
	include_bodies: true,
});

const originalMessage = inbox.find((m) => m.id === 123);

// Reply
await reply_message({
	project_key: "D:\\PATH\\TO\\PROJECT",
	message_id: originalMessage.id,
	sender_name: "YourAgentName",
	body_md: `## Response

Your response here...`,
});
```

## Search Templates

### Basic Search

```javascript
const results = await search_messages({
	project_key: "D:\\PATH\\TO\\PROJECT",
	query: "authentication security",
	limit: 50,
});

console.log(`Found ${results.length} messages`);
results.forEach((r) => {
	console.log(`${r.from}: ${r.subject} (${r.created_ts})`);
});
```

### Advanced Search

```javascript
// Boolean operators
const results = await search_messages({
	project_key: "D:\\PATH\\TO\\PROJECT",
	query: "(authentication OR auth) AND NOT deprecated",
	limit: 50,
});

// Phrase search
const results = await search_messages({
	project_key: "D:\\PATH\\TO\\PROJECT",
	query: '"token refresh" AND oauth2',
	limit: 50,
});

// Field-specific (if FTS5 configured)
const results = await search_messages({
	project_key: "D:\\PATH\\TO\\PROJECT",
	query: "subject:bug AND body:crash",
	limit: 50,
});
```

## Cross-Project Templates

### Establish Cross-Project Contact

```javascript
// Project A: Backend
await request_contact({
	project_key: "D:\\PATH\\TO\\BACKEND",
	from_agent: "BackendAgent",
	to_agent: "FrontendAgent",
	to_project: "D:\\PATH\\TO\\FRONTEND",
	reason: "API integration coordination",
	ttl_seconds: 604800, // 1 week
});

// Project B: Frontend
await respond_contact({
	project_key: "D:\\PATH\\TO\\FRONTEND",
	to_agent: "FrontendAgent",
	from_agent: "BackendAgent",
	from_project: "D:\\PATH\\TO\\BACKEND",
	accept: true,
	ttl_seconds: 604800,
});
```

### Send Cross-Project Message

```javascript
// After contact established
await send_message({
	project_key: "D:\\PATH\\TO\\BACKEND", // Your project
	sender_name: "BackendAgent",
	to: ["FrontendAgent"], // Agent in different project
	subject: "[API-123] New endpoint available",
	body_md: `## New Endpoint

POST /api/users/search
...`,
	thread_id: "API-123",
});
```

## Conflict Resolution Templates

### Check for Conflicts Before Reserving

```javascript
// Attempt reservation
const result = await file_reservation_paths({
	project_key: "D:\\PATH\\TO\\PROJECT",
	agent_name: "YourAgentName",
	paths: ["src/module/**"],
	exclusive: true,
	ttl_seconds: 3600,
});

// Handle conflicts
if (result.conflicts.length > 0) {
	console.log("Conflicts detected:");
	result.conflicts.forEach((c) => {
		console.log(`- ${c.agent_name} has ${c.path_pattern}`);
		console.log(`  Expires: ${c.expires_ts}`);
		console.log(`  Exclusive: ${c.exclusive}`);
	});

	// Option 1: Contact conflicting agent
	const conflict = result.conflicts[0];
	await send_message({
		project_key: "D:\\PATH\\TO\\PROJECT",
		sender_name: "YourAgentName",
		to: [conflict.agent_name],
		subject: "Coordination needed for src/module",
		body_md: `I need to work on src/module/** for TASK-123.

Your reservation expires: ${conflict.expires_ts}

Can we coordinate? Or can you release early if you're done?`,
		importance: "high",
		ack_required: true,
	});

	// Option 2: Use non-exclusive if just reading
	await file_reservation_paths({
		project_key: "D:\\PATH\\TO\\PROJECT",
		agent_name: "YourAgentName",
		paths: ["src/module/**"],
		exclusive: false,
		ttl_seconds: 1800,
		reason: "TASK-123: Code review (read-only)",
	});

	// Option 3: Wait for expiry
	const waitTime = new Date(conflict.expires_ts) - new Date();
	console.log(`Waiting ${waitTime}ms for reservation to expire`);
	await new Promise((resolve) => setTimeout(resolve, waitTime));
	// Retry reservation
}
```

### Force Release Stale Reservation

```javascript
// Only use when reservation is genuinely stale
await force_release_file_reservation({
	project_key: "D:\\PATH\\TO\\PROJECT",
	agent_name: "YourAgentName",
	file_reservation_id: 123,
	notify_previous: true,
	note: "Emergency: Critical bug requires immediate access to these files. Your reservation appeared inactive (no git/fs/mail activity). Please reach out if you were still working on this.",
});
```

## Cleanup Templates

### End of Session Cleanup

```javascript
// Release all reservations
await release_file_reservations({
	project_key: "D:\\PATH\\TO\\PROJECT",
	agent_name: "YourAgentName",
});

// Send completion message
await send_message({
	project_key: "D:\\PATH\\TO\\PROJECT",
	sender_name: "YourAgentName",
	to: ["TeamLead"],
	subject: "Session complete: Task summary",
	body_md: `## Work Completed

Summary of work done...

## Files Modified
- List of files

## Next Steps
What's next...`,
	thread_id: "SESSION-" + Date.now(),
});
```

### Periodic Status Check

```javascript
// Every 30 minutes during long-running work
setInterval(async () => {
	// Renew reservations
	await renew_file_reservations({
		project_key: "D:\\PATH\\TO\\PROJECT",
		agent_name: "YourAgentName",
		extend_seconds: 1800,
	});

	// Check for urgent messages
	const urgent = await fetch_inbox({
		project_key: "D:\\PATH\\TO\\PROJECT",
		agent_name: "YourAgentName",
		urgent_only: true,
		include_bodies: false,
	});

	if (urgent.length > 0) {
		console.log(`${urgent.length} urgent messages!`);
		// Handle urgent items...
	}
}, 1800000); // 30 minutes
```

# Workflow Patterns

Common patterns for using MCP Agent Mail effectively in multi-agent environments.

## Table of Contents

- [Workflow Patterns](#workflow-patterns)
	- [Table of Contents](#table-of-contents)
	- [Single Agent Session](#single-agent-session)
	- [Multi-Agent Feature Development](#multi-agent-feature-development)
	- [Bug Fix Coordination](#bug-fix-coordination)
	- [Code Review Workflow](#code-review-workflow)
	- [Emergency Response](#emergency-response)
	- [Cross-Repository Integration](#cross-repository-integration)
	- [Long-Running Refactoring](#long-running-refactoring)
	- [Best Practices from Patterns](#best-practices-from-patterns)
		- [Always Reserve Before Editing](#always-reserve-before-editing)
		- [Use Descriptive Thread IDs](#use-descriptive-thread-ids)
		- [Acknowledge Important Messages](#acknowledge-important-messages)
		- [Regular Status Updates](#regular-status-updates)
		- [Release Promptly](#release-promptly)
		- [Handle Conflicts Gracefully](#handle-conflicts-gracefully)
		- [Cross-Project Coordination](#cross-project-coordination)
		- [Emergency Procedures](#emergency-procedures)

## Single Agent Session

Basic workflow for a single agent working independently.

```javascript
// 1. Start session
const session = macro_start_session({
  human_key: "/excalibur/dispatch",
  program: "Claude Code",
  model: "claude-sonnet-4",
  task_description: "Implement user profile page",
  file_reservation_paths: ["src/pages/profile/**", "src/components/Profile/**"],
  file_reservation_ttl_seconds: 7200,
  inbox_limit: 20
})

// 2. Check for urgent messages
const urgentMessages = session.inbox.filter(m => m.importance === "high" || m.importance === "urgent")
if (urgentMessages.length > 0) {
  // Handle urgent messages first
  urgentMessages.forEach(msg => {
    acknowledge_message({
      project_key: "D:\\Excalibur.Dispatch",
      agent_name: session.agent.name,
      message_id: msg.id
    })
  })
}

// 3. Work on task
// ... make code changes ...

// 4. Periodically renew reservation if needed
renew_file_reservations({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: session.agent.name,
  extend_seconds: 3600
})

// 5. Complete work
release_file_reservations({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: session.agent.name
})

// 6. Announce completion
send_message({
  project_key: "D:\\Excalibur.Dispatch",
  sender_name: session.agent.name,
  to: ["TeamLead"],
  subject: "Completed: User profile page",
  body_md: `## Summary

Implemented user profile page with:
- Profile editing
- Avatar upload
- Password change
- Account deletion

Ready for review.`,
  thread_id: "FEAT-789",
  ack_required: true
})
```

## Multi-Agent Feature Development

Coordinating multiple agents working on related features.

```javascript
// Backend Agent
// 1. Start and reserve API layer
macro_start_session({
  human_key: "/excalibur/dispatch",
  program: "Claude Code",
  model: "claude-sonnet-4",
  task_description: "Backend: User search API",
  agent_name: "BackendAgent",
  file_reservation_paths: ["src/api/users/**", "src/services/search/**"],
  file_reservation_ttl_seconds: 3600
})

// 2. Announce start
send_message({
  project_key: "D:\\Excalibur.Dispatch",
  sender_name: "BackendAgent",
  to: ["FrontendAgent"],
  subject: "[FEAT-456] Starting user search API",
  body_md: `## API Design

POST /api/users/search
- Query parameters: q, filters, page, limit
- Returns: { users: [], pagination: {} }

ETA: 2 hours`,
  thread_id: "FEAT-456",
  ack_required: true
})

// 3. Implement API
// ... code changes ...

// 4. Notify completion
send_message({
  project_key: "D:\\Excalibur.Dispatch",
  sender_name: "BackendAgent",
  to: ["FrontendAgent"],
  subject: "[FEAT-456] API ready for integration",
  body_md: `## Completed

API endpoint deployed:
- URL: POST /api/users/search
- Auth: Bearer token required
- Docs: /api/docs/users/search

Ready for frontend integration.`,
  thread_id: "FEAT-456",
  ack_required: true
})

// Frontend Agent
// 1. Start and wait for backend
macro_start_session({
  human_key: "/excalibur/dispatch",
  program: "Claude Code",
  model: "claude-sonnet-4",
  task_description: "Frontend: User search UI",
  agent_name: "FrontendAgent",
  file_reservation_paths: ["src/components/Search/**", "src/hooks/useSearch.ts"]
})

// 2. Check for backend completion
const inbox = fetch_inbox({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "FrontendAgent",
  include_bodies: true
})

const backendReady = inbox.find(m =>
  m.thread_id === "FEAT-456" &&
  m.subject.includes("API ready")
)

if (backendReady) {
  // 3. Acknowledge and proceed
  acknowledge_message({
    project_key: "D:\\Excalibur.Dispatch",
    agent_name: "FrontendAgent",
    message_id: backendReady.id
  })

  // 4. Implement UI
  // ... code changes ...

  // 5. Notify completion
  send_message({
    project_key: "D:\\Excalibur.Dispatch",
    sender_name: "FrontendAgent",
    to: ["BackendAgent", "TeamLead"],
    subject: "[FEAT-456] Completed: Search UI integrated",
    body_md: `## Summary

Implemented search UI:
- Search input with debounce
- Filter controls
- Results list with pagination
- Loading and error states

Feature complete and ready for QA.`,
    thread_id: "FEAT-456"
  })
}
```

## Bug Fix Coordination

Handling urgent bugs with clear communication.

```javascript
// 1. Human overseer reports bug
// (Sent via Web UI by human operator)
// From: HumanOverseer
// Subject: "URGENT: Production bug - user login failing"
// Thread: BUG-789

// 2. Agent receives and processes
const inbox = fetch_inbox({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "GreenCastle",
  urgent_only: true
})

const bugReport = inbox.find(m => m.from === "HumanOverseer")

// 3. Acknowledge immediately
acknowledge_message({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "GreenCastle",
  message_id: bugReport.id
})

// 4. Release current work
release_file_reservations({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "GreenCastle"
})

// 5. Reserve bug-related files
file_reservation_paths({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "GreenCastle",
  paths: ["src/auth/**", "tests/auth/**"],
  exclusive: true,
  reason: "BUG-789: Fixing production login issue",
  ttl_seconds: 1800
})

// 6. Investigate and fix
// ... debugging and fixes ...

// 7. Report progress
send_message({
  project_key: "D:\\Excalibur.Dispatch",
  sender_name: "GreenCastle",
  to: ["HumanOverseer"],
  subject: "Re: URGENT: Production bug - user login failing",
  body_md: `## Investigation

Root cause: JWT expiration not handled correctly

Fix applied:
- Added token refresh logic
- Improved error messaging
- Added tests

Deploying to staging for verification.`,
  thread_id: "BUG-789",
  importance: "high"
})

// 8. After fix verified, report completion
send_message({
  project_key: "D:\\Excalibur.Dispatch",
  sender_name: "GreenCastle",
  to: ["HumanOverseer"],
  subject: "Re: URGENT: Production bug - RESOLVED",
  body_md: `## Resolution

Bug fixed and deployed to production:
- Commit: abc123
- Tests passing
- Monitoring shows login success rate back to 99.9%

Resuming original work on FEAT-456.`,
  thread_id: "BUG-789"
})

// 9. Release and resume
release_file_reservations({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "GreenCastle"
})
```

## Code Review Workflow

Structured code review with file reservations.

```javascript
// Author Agent
// 1. Complete feature
send_message({
  project_key: "D:\\Excalibur.Dispatch",
  sender_name: "AuthorAgent",
  to: ["ReviewerAgent"],
  subject: "[FEAT-123] Ready for review: Authentication module",
  body_md: `## Changes

Implemented OAuth2 authentication:
- Login/logout endpoints
- Token refresh
- Session management

Files changed:
- src/auth/oauth.ts
- src/auth/session.ts
- tests/auth/*.test.ts

Please review.`,
  thread_id: "FEAT-123",
  ack_required: true
})

// Reviewer Agent
// 1. Receive review request
const inbox = fetch_inbox({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "ReviewerAgent",
  include_bodies: true
})

const reviewRequest = inbox.find(m =>
  m.from === "AuthorAgent" &&
  m.subject.includes("Ready for review")
)

// 2. Reserve files for read-only review
file_reservation_paths({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "ReviewerAgent",
  paths: ["src/auth/**", "tests/auth/**"],
  exclusive: false,  // Non-exclusive for reading
  reason: "FEAT-123: Code review",
  ttl_seconds: 1800
})

// 3. Perform review
// ... analyze code ...

// 4. Provide feedback
send_message({
  project_key: "D:\\Excalibur.Dispatch",
  sender_name: "ReviewerAgent",
  to: ["AuthorAgent"],
  subject: "Re: [FEAT-123] Review feedback",
  body_md: `## Review Feedback

Overall: Good implementation. Minor issues:

**Issues:**
1. Token refresh logic should handle edge case (line 45)
2. Missing error handling in logout (line 78)
3. Test coverage for session timeout needed

**Suggestions:**
- Consider adding rate limiting
- Document token expiration policy

Please address issues 1-3, suggestions optional.`,
  thread_id: "FEAT-123",
  ack_required: true
})

// 5. Release review reservation
release_file_reservations({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "ReviewerAgent",
  paths: ["src/auth/**", "tests/auth/**"]
})

// Author Agent
// 6. Address feedback
acknowledge_message({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "AuthorAgent",
  message_id: reviewFeedback.id
})

file_reservation_paths({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "AuthorAgent",
  paths: ["src/auth/**", "tests/auth/**"],
  exclusive: true,
  reason: "FEAT-123: Addressing review feedback",
  ttl_seconds: 1800
})

// ... make changes ...

send_message({
  project_key: "D:\\Excalibur.Dispatch",
  sender_name: "AuthorAgent",
  to: ["ReviewerAgent"],
  subject: "Re: [FEAT-123] Review feedback addressed",
  body_md: `## Changes Made

1. ✅ Fixed token refresh edge case
2. ✅ Added error handling in logout
3. ✅ Added session timeout tests
4. ✅ Added rate limiting
5. ✅ Documented token policy

Ready for re-review.`,
  thread_id: "FEAT-123",
  ack_required: true
})
```

## Emergency Response

Handling critical issues with priority escalation.

```javascript
// Detection Agent
// 1. Detect critical issue
send_message({
  project_key: "D:\\Excalibur.Dispatch",
  sender_name: "MonitoringAgent",
  to: ["OnCallAgent", "TeamLead", "HumanOverseer"],
  subject: "🚨 CRITICAL: Database connection pool exhausted",
  body_md: `## Alert

Severity: CRITICAL
Service: API Server
Issue: Database connection pool exhausted

Metrics:
- Active connections: 100/100
- Failed requests: 45% (last 5min)
- Error rate: 2500/min

Immediate action required.`,
  importance: "urgent",
  ack_required: true
})

// OnCall Agent
// 1. Receive alert
const alerts = fetch_inbox({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "OnCallAgent",
  urgent_only: true
})

// 2. Acknowledge and claim
acknowledge_message({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "OnCallAgent",
  message_id: alerts[0].id
})

// 3. Force release stale reservations if needed
const reservations = /* query resource://file_reservations */

const staleReservation = reservations.find(r =>
  r.path_pattern.includes("src/database/**") &&
  r.agent_name !== "OnCallAgent"
)

if (staleReservation) {
  force_release_file_reservation({
    project_key: "D:\\Excalibur.Dispatch",
    agent_name: "OnCallAgent",
    file_reservation_id: staleReservation.id,
    notify_previous: true,
    note: "Emergency: Database issue requires immediate attention"
  })
}

// 4. Reserve emergency access
file_reservation_paths({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "OnCallAgent",
  paths: ["src/database/**", "config/database.yml"],
  exclusive: true,
  reason: "CRITICAL: Database connection pool issue",
  ttl_seconds: 900
})

// 5. Investigate and apply hotfix
// ... emergency fixes ...

// 6. Report status updates
send_message({
  project_key: "D:\\Excalibur.Dispatch",
  sender_name: "OnCallAgent",
  to: ["MonitoringAgent", "TeamLead", "HumanOverseer"],
  subject: "Re: 🚨 CRITICAL - Status Update",
  body_md: `## Status Update (T+5min)

Investigation:
- Root cause: Connection leak in analytics query
- Temporary fix: Restarted service (connections reset)
- Permanent fix: Added connection timeout

Current status:
- Error rate: <1%
- Active connections: 25/100
- Service stable

Monitoring for 30min before closing.`,
  importance: "urgent"
})

// 7. After stabilization
send_message({
  project_key: "D:\\Excalibur.Dispatch",
  sender_name: "OnCallAgent",
  to: ["MonitoringAgent", "TeamLead", "HumanOverseer"],
  subject: "Re: 🚨 CRITICAL - RESOLVED",
  body_md: `## Incident Resolution

Duration: 15 minutes
Impact: 45% request failure rate

Actions taken:
1. Identified connection leak
2. Applied hotfix with timeout
3. Restarted service
4. Monitored for 30min

Status: RESOLVED
- Service stable
- Error rate normal
- No data loss

Follow-up:
- PR #456 with permanent fix
- Post-mortem scheduled`,
  importance: "high"
})

release_file_reservations({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "OnCallAgent"
})
```

## Cross-Repository Integration

Coordinating across frontend and backend repositories.

```javascript
// Backend Repository (D:\Projects\API-Backend)
// Backend Agent
macro_start_session({
  human_key: "/excalibur/dispatch",
  program: "Claude Code",
  model: "claude-sonnet-4",
  task_description: "New payment API endpoints",
  agent_name: "BackendAgent",
  file_reservation_paths: ["src/controllers/payment/**", "src/services/stripe/**"]
})

// Request contact with frontend agent
request_contact({
  project_key: "D:\\Projects\\API-Backend",
  from_agent: "BackendAgent",
  to_agent: "FrontendAgent",
  to_project: "D:\\Projects\\Web-Frontend",
  reason: "Payment API integration for FEAT-890"
})

// Frontend Repository (D:\Projects\Web-Frontend)
// Frontend Agent
macro_start_session({
  human_key: "/excalibur/dispatch",
  program: "Claude Code",
  model: "claude-sonnet-4",
  task_description: "Payment UI integration",
  agent_name: "FrontendAgent"
})

// Check for contact requests
const inbox = fetch_inbox({
  project_key: "D:\\Projects\\Web-Frontend",
  agent_name: "FrontendAgent"
})

const contactRequest = inbox.find(m =>
  m.from === "BackendAgent" &&
  m.subject.includes("contact request")
)

// Approve contact
respond_contact({
  project_key: "D:\\Projects\\Web-Frontend",
  to_agent: "FrontendAgent",
  from_agent: "BackendAgent",
  from_project: "D:\\Projects\\API-Backend",
  accept: true,
  ttl_seconds: 604800  // 1 week
})

// Now agents can message across projects
// Backend Agent
send_message({
  project_key: "D:\\Projects\\API-Backend",
  sender_name: "BackendAgent",
  to: ["FrontendAgent"],  // In different project
  subject: "[FEAT-890] Payment API specification",
  body_md: `## API Contract

### Create Payment Intent
POST /api/payments/intent
Request: { amount, currency, metadata }
Response: { clientSecret, intentId }

### Confirm Payment
POST /api/payments/confirm
Request: { intentId, paymentMethodId }
Response: { status, transactionId }

Questions or concerns?`,
  thread_id: "FEAT-890",
  ack_required: true
})

// Frontend Agent (in different repo) can reply
send_message({
  project_key: "D:\\Projects\\Web-Frontend",
  sender_name: "FrontendAgent",
  to: ["BackendAgent"],
  subject: "Re: [FEAT-890] Payment API specification",
  body_md: `## Questions

1. What's the timeout for intent expiration?
2. Do we need webhook for async confirmation?
3. Error codes for different failure modes?

Starting UI implementation while awaiting answers.`,
  thread_id: "FEAT-890"
})
```

## Long-Running Refactoring

Managing extended refactoring with multiple checkpoint messages.

```javascript
// 1. Start refactoring
macro_start_session({
  human_key: "/excalibur/dispatch",
  program: "Claude Code",
  model: "claude-sonnet-4",
  task_description: "Refactor: Service layer to use dependency injection",
  agent_name: "RefactorAgent",
  file_reservation_paths: ["src/services/**", "src/di/**", "tests/services/**"],
  file_reservation_ttl_seconds: 14400  // 4 hours
})

// 2. Announce plan
send_message({
  project_key: "D:\\Excalibur.Dispatch",
  sender_name: "RefactorAgent",
  to: ["TeamLead"],
  subject: "[REFACTOR-456] Starting: DI migration",
  body_md: `## Refactoring Plan

Scope: Migrate 15 service classes to DI

Phases:
1. ✅ Create DI container
2. ⏳ Migrate core services (5 classes)
3. ⏳ Migrate feature services (8 classes)
4. ⏳ Migrate utility services (2 classes)
5. ⏳ Update tests
6. ⏳ Remove legacy factories

ETA: 3-4 hours
Will send updates every hour.`,
  thread_id: "REFACTOR-456",
  ack_required: true
})

// 3. First checkpoint (after 1 hour)
renew_file_reservations({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "RefactorAgent",
  extend_seconds: 3600
})

send_message({
  project_key: "D:\\Excalibur.Dispatch",
  sender_name: "RefactorAgent",
  to: ["TeamLead"],
  subject: "[REFACTOR-456] Checkpoint 1: Core services migrated",
  body_md: `## Progress (T+1h)

Completed:
- ✅ DI container implemented
- ✅ Core services migrated (5/5)
- ✅ Core service tests passing

Next:
- Feature services (0/8)

ETA: 2-3 hours remaining`,
  thread_id: "REFACTOR-456"
})

// 4. Second checkpoint (after 2 hours)
renew_file_reservations({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "RefactorAgent",
  extend_seconds: 3600
})

send_message({
  project_key: "D:\\Excalibur.Dispatch",
  sender_name: "RefactorAgent",
  to: ["TeamLead"],
  subject: "[REFACTOR-456] Checkpoint 2: Feature services in progress",
  body_md: `## Progress (T+2h)

Completed:
- ✅ Feature services migrated (8/8)
- ✅ Feature service tests passing

Next:
- Utility services (0/2)
- Legacy factory cleanup

ETA: 1-2 hours remaining`,
  thread_id: "REFACTOR-456"
})

// 5. Completion
send_message({
  project_key: "D:\\Excalibur.Dispatch",
  sender_name: "RefactorAgent",
  to: ["TeamLead"],
  subject: "[REFACTOR-456] COMPLETED: DI migration",
  body_md: `## Refactoring Complete

Summary:
- ✅ 15 service classes migrated
- ✅ DI container operational
- ✅ All tests passing (236/236)
- ✅ Legacy factories removed
- ✅ Documentation updated

Changes:
- 45 files modified
- +1200 / -950 lines
- 0 breaking changes

Ready for review.`,
  thread_id: "REFACTOR-456"
})

release_file_reservations({
  project_key: "D:\\Excalibur.Dispatch",
  agent_name: "RefactorAgent"
})
```

## Best Practices from Patterns

### Always Reserve Before Editing

Every workflow starts with file reservations before making changes.

### Use Descriptive Thread IDs

Thread IDs like "FEAT-456", "BUG-789", "REFACTOR-123" provide context and enable cross-reference with external task trackers.

### Acknowledge Important Messages

Always acknowledge messages with `ack_required: true`, especially from HumanOverseer.

### Regular Status Updates

For long-running tasks, send checkpoint messages every hour to keep stakeholders informed.

### Release Promptly

Release file reservations immediately after completing work or when blocked.

### Handle Conflicts Gracefully

When file reservation conflicts occur, communicate with the conflicting agent rather than forcing release.

### Cross-Project Coordination

Establish explicit contact links before messaging agents in different projects.

### Emergency Procedures

For critical issues, use `force_release_file_reservation` with notification to quickly unblock work.

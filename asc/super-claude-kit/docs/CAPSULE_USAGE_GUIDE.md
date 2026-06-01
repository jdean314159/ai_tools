# Context Capsule - Claude Code Usage Guide

## For Claude: How to Use This System Effectively

This guide is specifically for Claude Code (me!) on how to leverage the Context Capsule system to maximize efficiency and context awareness.

## 🎯 Core Principle

**Before re-reading files or re-checking status, check the capsule first!**

The capsule injection appears automatically before each prompt. Use it to:
- Avoid re-reading files I accessed recently
- Remember current task without TodoWrite lookup
- Know git state without running git commands
- Recall sub-agent findings
- Reference discoveries made earlier in session

## 📋 Auto-Logging (Automatic Context Tracking)

**NEW: File access and sub-agent results are logged automatically!**

The PostToolUse hook automatically logs:
- Read operations
- Edit operations
- Write operations
- Task tool (sub-agent) completions
- TodoWrite task updates

**You no longer need to manually call log-file-access.sh or log-subagent.sh!**

### What Gets Logged Automatically:

**File Operations:**
- Read tool automatically logs to session_files.log
- Edit tool automatically logs to session_files.log
- Write tool automatically logs to session_files.log

**Sub-Agent Results:**
- Task tool automatically logs to session_subagents.log
- Summary extracted from agent output (first 200 chars)

**Task Updates:**
- TodoWrite automatically logs in_progress tasks to session_tasks.log

### Manual Logging (Still Supported)

You can still manually log if needed:

```bash
# Optional: Manual file logging (if PostToolUse hook disabled)
./.claude/hooks/log-file-access.sh "path/to/file" "read|edit|write"

# Optional: Manual sub-agent logging (if PostToolUse hook disabled)
./.claude/hooks/log-subagent.sh "Explore" "Found important patterns"
```

### Required Manual Logging:

**Discoveries (Still Manual):**
You must manually log discoveries - Claude decides what's important:

```bash
# Pattern discoveries
./.claude/hooks/log-discovery.sh "pattern" "All hooks use set -euo pipefail"

# Architectural insights
./.claude/hooks/log-discovery.sh "architecture" "System uses microservices"

# Important decisions
./.claude/hooks/log-discovery.sh "decision" "Using JWT for authentication"
```

**Task Status (If Not Using TodoWrite):**
```bash
./.claude/hooks/log-task.sh "in_progress" "Implementing auth system"
```

### 3. After Key Discoveries

**Log insights, patterns, decisions as I learn:**

```bash
# Discovered a code pattern
./.claude/hooks/log-discovery.sh "pattern" "All hooks use 'set -euo pipefail' for safety"

# Had an important realization
./.claude/hooks/log-discovery.sh "insight" "TOON format reduces tokens by 52% vs JSON"

# Made a design decision
./.claude/hooks/log-discovery.sh "decision" "Using git diff for change detection over timestamps"

# Found architectural detail
./.claude/hooks/log-discovery.sh "architecture" "Frontend uses Smart API Client pattern"

# Identified a bug
./.claude/hooks/log-discovery.sh "bug" "Session hooks not catching sub-agent completions"

# Found optimization opportunity
./.claude/hooks/log-discovery.sh "optimization" "Parallel tool calls reduce latency by 40%"
```

**When to log:**
- ✅ When I understand how something works
- ✅ When I make an important decision
- ✅ When I find a pattern worth remembering
- ✅ When I identify bugs or optimizations
- ❌ Skip obvious/trivial observations

### 4. After TodoWrite Updates

**Sync tasks with capsule:**

```bash
# After using TodoWrite tool, log current state
./.claude/hooks/log-task.sh "in_progress" "Implementing Phase 3 features"
./.claude/hooks/log-task.sh "pending" "Test cross-session persistence"
./.claude/hooks/log-task.sh "completed" "Design automatic discovery extraction"
```

**When to log:**
- ✅ After marking task as in_progress (so capsule shows current work)
- ✅ After completing major tasks
- ❌ Skip for every single todo update (too noisy)

## 🐝 Shared Team Capsule

- `<files-in-context>` now includes `profile="worker"` so you can see who touched a file last.
- `<team-tasks>` and `<team-discoveries>` summarize other workers' updates from the past 48 hours—read them before repeating work.
- `.claude/shared/` stores the JSONL hive logs with file locks; `prune-shared-logs.sh` keeps only the newest 48 hours automatically.

## 👤 Worker Profiles

- Launch each CLI window with `CLAUDE_WORKER_PROFILE=<name> claude` to load `~/.claude/workers/<name>.md` (or `<name>/role.md`).
- The resolved instructions are cached in `.claude/sessions/<CLAUDE_SESSION_ID>/current_worker_message.txt`, so SessionStart/UserPrompt hooks reuse the same persona text.
- Copy `~/.claude/workers/default.md` to create backend/frontend/etc. workers that still contribute to the shared capsule.
- Include a `worker-identity` block in your frontmatter. The hooks parse it, remind you of the preferred name + Agent Mail mailbox, and export helper environment variables (`CLAUDE_AGENT_MAILBOX`, `CLAUDE_WORKER_TEMP_PREFIX`, `CLAUDE_WORKER_REGISTER_WITH_MAIL`).
- Use the prefix when creating Agent Mail helper files: `tmp_agentmail_${CLAUDE_WORKER_TEMP_PREFIX}_*.json` (hooks clean them at session start/end so collisions disappear automatically).
- If `register_with_agent_mail: true`, the session automatically registers you with Agent Mail at session start. Set ` New messages create `<agent-mail-alert>` blocks before each response until you process the inbox and run `./.claude/hooks/ack-worker-mail-alert.sh`.
- If `uses_beads: true`, session start automatically runs `bd quickstart` and `bd ready --json`, writing output to `.claude/beads/quickstart.log` and showing the tail in the worker banner.

## 🚀 Efficient Workflow Pattern

### Starting a Task

1. **Check capsule** - What's already in context?
2. **Log current task** - Mark it in_progress
3. **Work on task** - Read files, make changes
4. **Log file operations** - Track what I accessed
5. **Log discoveries** - Capture insights as they occur
6. **Complete task** - Log as completed

### Using Sub-Agents

1. **Launch sub-agent** via Task tool
2. **Wait for completion**
3. **Read sub-agent result**
4. **Log key findings** with log-subagent.sh
5. **Continue work** using those findings

### 🔒 Sub-Agent Production Safety

**All sub-agents are read-only for production safety:**

**✅ Sub-agents CAN:**
- Read files (Read tool)
- Search code (Grep tool)
- Find files (Glob tool)
- Fetch web content (WebFetch - architecture-explorer only)

**❌ Sub-agents CANNOT:**
- Execute bash commands (Bash tool removed)
- Modify files (no Edit/Write tools)
- Delete files
- Run destructive operations

**Why?** Sub-agents analyze and explore code but should never modify it. This prevents accidental file modifications in production environments.

### Example Session Flow

```
[Session starts - capsule initializes]

User: "Implement authentication system"

Me:
1. Check capsule → See I'm on epic/auth branch, 5 dirty files
2. Log task → "in_progress|Implementing authentication system"
3. Launch Explore agent to find existing auth code
4. Agent completes → Log: "Explore|Found auth in server/src/auth/"
5. Read auth files → Log file access for each
6. Make discovery → Log: "architecture|Uses JWT + Redis session store"
7. Implement feature → Log edits
8. Complete → Log: "completed|Implementing authentication system"

[Next prompt - capsule shows all this context!]
```

## 💡 Reading the Capsule

When I see the capsule, I should:

**🌿 Git State:**
- Check branch to ensure I'm on correct one
- Note dirty file count (indicates uncommitted work)
- Check ahead/behind to know sync status

**📁 Files in Context:**
- AVOID re-reading files shown here (unless >10m old)
- Use this to build mental model of codebase
- Reference these files when explaining to user

**✅ Current Tasks:**
- Always acknowledge the in_progress task
- Prioritize current task over new work
- Reference completed tasks when explaining progress

**🤖 Sub-Agent Results:**
- Recall findings instead of re-exploring
- Build on previous discoveries
- Avoid duplicate sub-agent calls

**💡 Session Discoveries:**
- Reference these insights in my responses
- Build on patterns discovered
- Maintain consistency with decisions made

**⏱️ Session Info:**
- Note message count (high count = long session)
- Consider session duration for context freshness

## 🎨 Best Practices

### DO ✅
- Log after every major tool use (Read/Edit/Write)
- Capture sub-agent results immediately
- Note architectural discoveries as I learn
- Sync TodoWrite status when changing tasks
- Check capsule before redundant operations
- Log decisions so I remember rationale

### DON'T ❌
- Log trivial operations (quick bash commands)
- Over-log discoveries (keep signal-to-noise high)
- Ignore capsule (defeats the purpose!)
- Re-read files shown in capsule
- Launch duplicate sub-agents
- Forget to log current task status

## 🔄 Self-Correction Pattern

If I realize I should have logged something:

```bash
# Retroactively log file access
./.claude/hooks/log-file-access.sh "path/to/file" "read"

# Capture late discovery
./.claude/hooks/log-discovery.sh "insight" "What I just realized"

# Update task status
./.claude/hooks/log-task.sh "in_progress" "Current task"
```

## 📊 Measuring Success

Good capsule usage means:
- **Fewer redundant file reads** - If capsule shows I read it 2m ago, don't read again
- **Better task continuity** - Always see current work without asking
- **Richer context** - User sees my discoveries in capsule
- **Faster responses** - Less time re-gathering context
- **Better memory** - Sub-agent findings persist across messages

## 🎯 Quick Reference

```bash
# File access
./.claude/hooks/log-file-access.sh "<path>" "read|edit|write"

# Sub-agent
./.claude/hooks/log-subagent.sh "<type>" "<summary>"

# Discovery
./.claude/hooks/log-discovery.sh "<category>" "<content>"
# Categories: pattern, insight, decision, architecture, bug, optimization

# Task
./.claude/hooks/log-task.sh "<status>" "<content>"
# Status: in_progress, pending, completed
```

## 🚦 When NOT to Use Capsule

- **Very first message** - Capsule might be empty
- **User asks to ignore context** - Respect explicit requests
- **Cross-session work** - Capsule resets each session (until Phase 3)
- **Simple queries** - Quick answers don't need heavy context

## 🎓 Learning from Usage

After each session, reflect:
- Did I avoid redundant file reads?
- Did I remember sub-agent findings?
- Did I maintain task awareness?
- Did I capture key discoveries?
- Did capsule help or was it noise?

Use this reflection to improve logging patterns.

---

**Remember**: The capsule is my external memory. Trust it, use it, maintain it!

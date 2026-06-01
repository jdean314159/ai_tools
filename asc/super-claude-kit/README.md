<p align="center">
  # Super Claude Kit
</p>

<p align="center">
  <img src="./.github/super_claude_kit.png" alt="Super Claude Kit" width="100%" />
</p>

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="https://claude.ai"><img src="https://img.shields.io/badge/Claude_Code-Compatible-blue.svg" alt="Claude Code"></a>
  <a href="https://github.com/arpitnath/super-claude-kit"><img src="https://img.shields.io/badge/version-1.2.0-blue.svg" alt="Version"></a>
</p>

<p align="center">
  <strong>Super Claude Kit</strong> adds persistent memory to Claude Code.
  <br/>
  <br/>
  A persistence layer for Claude Code.
  <br/>
  Files, tasks, discoveries — all restored instantly.
</p>

<p align="center">
  <code>curl -fsSL https://raw.githubusercontent.com/arpitnath/super-claude-kit/master/install | bash</code>
</p>

<p align="center">
  <img src="./.github/hero.gif" alt="Super Claude Kit" width="100%" />
</p>

---

## Quickstart

### Installing Super Claude Kit

Run the one-line installer:

```bash
curl -fsSL https://raw.githubusercontent.com/arpitnath/super-claude-kit/master/install | bash
```

That's it! Restart Claude Code and you'll see the context capsule on every session.

<details>
<summary>Manual installation (advanced)</summary>

```bash
# Clone the repository
git clone https://github.com/arpitnath/super-claude-kit.git
cd super-claude-kit

# Run the installer
bash install
```

The installer will:

- Install hooks to `.claude/hooks/`
- Build Go tools (dependency-scanner, progressive-reader)
- Configure `~/.claude/settings.local.json`
- Auto-install Go 1.23+ if not present

</details>

### What you get immediately

<p align="center">

  <img src="./.github/stats.png" alt="Session Resume" width="100%" />

</p>

**After installation, Claude Code will:**

- 🧠 **Remember files** you've accessed (no re-reads)
- 📦 **Restore context** between sessions (up to 24 hours)
- ✅ **Track tasks** across restarts
- 🔍 **Log discoveries** as you work
- 🔗 **Understand dependencies** in your codebase

### How it works

Super Claude Kit uses **hooks** (SessionStart, UserPromptSubmit) to:

1. **Capture context** as you work (file access, tasks, git state)
2. **Store in capsule** (`.claude/capsule.json`)
3. **Restore on restart** (automatic, zero manual input)

No configuration needed. It just works.

---

## Features

### 🧠 Persistent Memory

**Stop wasting tokens on re-reads.**

Vanilla Claude Code re-reads files on every question. Super Claude Kit tracks what's been read and references from memory.

---

### 📦 Context Capsule

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 CONTEXT CAPSULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🌿 Git State:
   Branch: feat/oauth (2 commits ahead)

📁 Files in Context:
   • auth/OAuthController.ts (read 2h ago)
   • config/google.ts (edited 1h ago)
   • routes/auth.ts (read 2h ago)

🔍 Discoveries:
   • Google OAuth requires state parameter
   • Token stored in httpOnly cookie

✅ Current Tasks:
   ⚡ Implementing OAuth callback handler
   ✓ Controller setup complete
   ✓ Google provider config added

💡 Previous session: 2 hours ago
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**See exactly what Claude remembers.** Every session start shows your capsule with:

- Git branch and commit status
- Files accessed with timestamps
- Discoveries logged during work
- Active and completed tasks
- Time since last session

The capsule uses TOON format for **52% token reduction** compared to JSON.

---

### 🐝 Worker Profiles & Hive Memory

- **Per-window personas**: export `CLAUDE_WORKER_PROFILE=backend-dev` before launching `claude` and the hooks will inject `~/.claude/workers/backend-dev.md` (or `backend-dev/role.md`) into the session system message.
- **Shared team logs**: every Read/Edit/Write/TodoWrite/Discovery entry streams into `.claude/shared/` with file locking, so all terminals see the same “Files in Context”, “Team Tasks”, and “Team Discoveries” no matter who touched the code.
- **Auto-pruned**: `prune-shared-logs.sh` trims entries older than 48 hours, keeping the hive memory current while preventing unbounded growth.
- **Identity + mailbox reminders**: worker frontmatter is parsed automatically-sessions start with a summary (preferred name, Agent Mail mailbox, registration flag, and required temp-file prefix) and environment variables such as `CLAUDE_AGENT_MAILBOX` and `CLAUDE_WORKER_TEMP_PREFIX`. Hooks clean up `tmp_agentmail_${CLAUDE_WORKER_TEMP_PREFIX}_*.json` at session start/end so each worker's files stay isolated.
- **Agent Mail integration**: if a worker's `worker-identity` block sets `register_with_agent_mail: true` and provides a mailbox, the session registers with Agent Mail at startup and fetches the inbox. Use the MCP Agent Mail `fetch_inbox` tool to check for new messages, and run `./.claude/hooks/ack-worker-mail-alert.sh` to clear alerts after processing.
- **Beads bootstrap**: workers can opt into Beads by setting `uses_beads: true`. Session start automatically runs `bd quickstart` and `bd ready --json`, records the output to `.claude/beads/quickstart.log`, and displays the latest lines so you don’t have to repeat the commands manually.
- **Bug discoveries -> Beads**: for workers with `uses_beads: true`, logging a `bug` discovery via `./.claude/hooks/log-discovery.sh bug "<details>"` automatically runs `bd create` to add a backlog item and records the attempt/outcome in `.claude/beads/bug-issues.log` for auditing.

Result: multiple Claude CLI windows can keep their specialized worker instructions while collaborating through a single capsule that tags which profile touched which files minutes ago.

---

### 🔗 Dependency Intelligence

<p align="center">

  <img src="./.github/dependency-graph.png" alt="Dependency Graph" width="100%" />

</p>

**Know what breaks before you break it.**

Built-in dependency scanner analyzes your codebase:

#### Available Commands

```bash
# Query what files import this file
.claude/tools/query-deps/query-deps.sh src/auth.ts

# Analyze impact of changing a file
.claude/tools/impact-analysis/impact-analysis.sh src/database.ts

# Find circular dependencies
.claude/tools/find-circular/find-circular.sh

# Identify unused files
.claude/tools/find-dead-code/find-dead-code.sh
```

#### Performance

- **1,000 files** scanned in <5 seconds
- **10,000 files** scanned in <30 seconds
- Supports TypeScript, JavaScript, Python, Go

---

### 🛠️ Built-in Tools

#### Progressive Reader

Read large files (>50KB) in semantic chunks using tree-sitter AST parsing.

```bash
# Read first chunk of a large file
progressive-reader --path src/large-file.ts

# List all chunks without content (preview)
progressive-reader --list --path src/large-file.ts

# Read specific chunk by index
progressive-reader --chunk 2 --path src/large-file.ts

# Continue from previous read (uses TOON token)
progressive-reader --continue-file /tmp/continue.toon
```

**Supported languages:** TypeScript, JavaScript, Python, Go

**When to use:**

- Files > 50KB that would consume too much context
- Reading sub-agent outputs progressively
- Large codebase exploration with minimal context usage

#### Dependency Scanner

Analyzes code structure and relationships using tree-sitter AST parsing.

```bash
# Build dependency graph
~/.claude/bin/dependency-scanner --path . --output .claude/dep-graph.toon
```

**Features:**

- Import/export tracking
- Circular dependency detection (Tarjan's algorithm)
- Impact analysis
- Dead code identification

---

### 🤖 Specialized Sub-Agents

Production-safe, read-only agents for common development tasks:

- **architecture-explorer** - Understand service boundaries and data flows
- **database-navigator** - Explore schemas, migrations, and relationships
- **agent-developer** - Build and debug AI agents with MCP integration
- **github-issue-tracker** - Create well-formatted issues from discoveries

All agents are sandboxed and require explicit permission for write operations.

---

## Docs & Guides

- **Getting Started**
  - [Installation & Verification](#installing-super-claude-kit)
  - [Understanding the Capsule](#-context-capsule)
  - [First Session Walkthrough](docs/CAPSULE_USAGE_GUIDE.md#first-session)
- **Usage Guide**
  - [File Access Logging](docs/CAPSULE_USAGE_GUIDE.md#file-logging)
  - [Task Tracking](docs/CAPSULE_USAGE_GUIDE.md#task-tracking)
  - [Discovery Logging](docs/CAPSULE_USAGE_GUIDE.md#discovery-logging)
  - [Best Practices](docs/CAPSULE_USAGE_GUIDE.md#best-practices)
- **Tools**
  - [Progressive Reader](docs/PROGRESSIVE_READER_ARCHITECTURE.md)
  - [Dependency Scanner](docs/DEPENDENCY_GRAPH_ARCHITECTURE.md)
  - [Custom Tools Guide](docs/CUSTOM_TOOLS.md)
- **Architecture**
  - [System Architecture](docs/SUPER_CLAUDE_SYSTEM_ARCHITECTURE.md)
  - [Hook System](docs/SUPER_CLAUDE_SYSTEM_ARCHITECTURE.md#hooks)
  - [Capsule Design](docs/SUPER_CLAUDE_SYSTEM_ARCHITECTURE.md#capsule)
  - [Sandboxing](docs/SANDBOXING_ARCHITECTURE.md)
- **Advanced**
  - [Configuration](docs/CONFIGURATION.md)
  - [Debug Mode](#debug-mode)
  - [Custom Hooks](docs/CUSTOM_HOOKS.md)
  - [Contributing](CONTRIBUTING.md)
- **Reference**
  - [CHANGELOG](CHANGELOG.md)
  - [FAQ](docs/FAQ.md)
  - [Troubleshooting](#troubleshooting)

---

## Requirements

- **Claude Code** (Desktop CLI or VSCode extension)
- **macOS** or **Linux** (Windows WSL supported)
- **Go 1.23+** (auto-installed if not present)
- **Bash 4.0+**

**Optional (for enhanced features):**

- **Git** - Provides branch tracking and git-aware change detection
  - Without git: Uses file modification time for change detection
  - All core features work without git

---

## Verification

After installation, verify everything works:

```bash
# Run comprehensive tests
bash .claude/scripts/test-super-claude.sh

# View current stats
bash .claude/scripts/show-stats.sh

# Check installed tools
~/.claude/bin/dependency-scanner --version
~/.claude/bin/progressive-reader --version
```

Expected output:

```
✅ Super Claude Kit v1.0.0
✅ dependency-scanner v1.0.0
✅ progressive-reader v1.0.0
✅ All hooks configured
✅ All tests passed
```

---

## Updating

### Check for Updates

```bash
bash .claude/scripts/update-super-claude.sh
```

### Development Mode

Install latest development version:

```bash
bash .claude/scripts/update-super-claude.sh --dev
```

---

## Configuration

### Quick Worker Setup

- Review `docs/QUICK_SETUP.md` for the fastest way to launch a worker in the CLI (environment variables, Agent Mail project key, poll interval, etc.).
- Summary:
  1. Install/update the kit (`bash install` or `bash .claude/scripts/update-super-claude.sh`).
  2. Export `CLAUDE_WORKER_PROFILE=<worker>` (e.g., `backend-developer`).
  3. Optionally set `CLAUDE_AGENT_MAIL_PROJECT_KEY=/your/project`.
  4. Run `CLAUDE_WORKER_PROFILE=<worker> claude` and follow the banner instructions (Beads snapshot, Agent Mail alerts).
  5. Clear alerts with `./.claude/hooks/ack-worker-mail-alert.sh` after processing inbox items.

### Language-Specific Tips

#### C# / .NET

- Build/test with `dotnet restore`, `dotnet build`, `dotnet test`. Architecture Explorer now lists `.sln`, `.csproj`, and `Program.cs` entry points so you can quickly map Dispatch vs Excalibur layers.
- Follow the consolidated test infrastructure in `tests/shared/Tests.Shared/` and the performance test guidance (`[Collection("Performance Tests")]`) when adding or refactoring suites.
- Cite ADRs (`management/architecture/*.md`) whenever architectural decisions (serialization, DI, performance constraints) influence your guidance or code changes.

#### Angular

- Use the workspace scripts in `angular.json` / `nx.json` (`ng test`, `ng build`, `nx test <project>`, `npm run lint`, etc.). Architecture Explorer now calls out Angular-specific entry points (`src/app/app.module.ts`, environments, tsconfig path aliases) to speed up discovery.
- Testing guidance lives in the Tests Developer profile: prefer Vitest for new tests, rely on Spectator helpers sparingly, and use `mockReturnValue()` conventions.
- When reorganizing modules/components, keep `src/app/**` structure, environment configs, and path aliases in sync so workers (and the CLI) can locate the right files during reviews.

### Settings Location

`.claude/settings.local.json`

```json
{
  "permissions": {
    "allow": [
      "Bash(git add:*)",
      "Bash(git commit:*)",
      "Bash(~/.claude/bin/dependency-scanner:*)",
      "Bash(progressive-reader:*)"
    ]
  },
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash -lc \"DIR=\\$(pwd); while [ \\\"\\$DIR\\\" != \\\"/\\\" ]; do if [ -d \\\"\\$DIR/.claude\\\" ]; then cd \\\"\\$DIR\\\" && exec .claude/hooks/session-start.sh; fi; DIR=\\$(dirname \\\"\\$DIR\\\"); done\""
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash -lc \"DIR=\\$(pwd); while [ \\\"\\$DIR\\\" != \\\"/\\\" ]; do if [ -d \\\"\\$DIR/.claude\\\" ]; then cd \\\"\\$DIR\\\" && exec .claude/hooks/pre-task-analysis.sh; fi; DIR=\\$(dirname \\\"\\$DIR\\\"); done\""
          }
        ]
      }
    ]
  }
}
```

> **Quiet hooks vs. file guards**
>
> - By default the installer now configures `PreToolUse` to match only `Task` (for dependency-tool nudges) and `PostToolUse` to match `TodoWrite|Task|Edit|Write`. This keeps the Claude CLI UI from printing duplicate prompts or spinner rows every time you run `Read`.
> - If you still want the large-file / redundant-read guardrails, set `SUPER_CLAUDE_ENABLE_READ_GUARDS=1` before running `install` (or provide explicit overrides with `SUPER_CLAUDE_PRE_TOOL_MATCHER` / `SUPER_CLAUDE_POST_TOOL_MATCHER`).
> - Re-run `install` after changing those env vars to regenerate `.claude/settings.local.json`.

### Project Slash Commands

Custom project commands now ship as flat files in `.claude/commands/` (the CLI currently discovers only root-level files) and are installed automatically into the target repo’s `.claude/commands/` directory. Invoke them directly inside the CLI (for example `/kickoff`):

- `/kickoff` – session warm-up ritual: restate focus, scan Agent Mail/beads/tasks logs, and write a concrete plan before touching tools.
- `/resume` – rehydrate context after getting interrupted by replaying shared logs, worker identity, and beads entries before planning the next steps.
- `/closeout` – capture results, run exit tests, update logs/discoveries, and draft the notification you owe the team before signing off.
- `/triage-tests` – reminds you to run tests in small batches, capture real command output, and record failures without flooding the console.
- `/run-current-tasks` – fetch mail/todos, execute assignments, and notify the team once tests (in small batches) pass.
- `/send-sprint-guidance [sprint]` – summarize sprint priorities after clearing mail/todos and broadcast guidance to the team.
- `/ready-for-testing [sprint]` – announce that developer work is ready for QA, then finish your assignments with batched tests and notify everyone.
- `/review-architect [sprint]` & `/review-project-reviewer [sprint]` – tailored checklists for SoftwareArchitect and ProjectReviewer reviews.
- `/ready-for-docs [sprint]` – kick off the documentation workflow once dev tasks land.
- `/plan-next-sprint [sprint]` – review backlog, run sprint planning, create/assign tasks, and notify assignees.
- `/close-sprint [sprint]` – final close-out: update `management/sprints`, close Beads tasks, and create the sprint review doc before announcing completion.

Add your own by creating Markdown files under `.claude/commands/<namespace>/<name>.md` (see [Slash commands](https://docs.anthropic.com/en/slash-commands) for syntax). Project commands always take precedence over user-level commands with the same name so your team can standardize workflows.

### Worker Profiles

- Worker instructions live in `~/.claude/workers/<profile>.md` (or `<profile>/role.md`). The installer ships a `default.md` template you can copy.
- Launch each CLI window with `CLAUDE_WORKER_PROFILE=<profile> CLAUDE_SESSION_ID=<custom-id> claude` (or run `bash .claude/scripts/run-worker.sh <profile>`). Each session id maps to `.claude/sessions/<id>/`, so multiple windows can run in parallel without clobbering each other.
- Profiles and their rendered system message are cached in `.claude/sessions/<session-id>/current_worker_message.txt`, so the same persona is reused across SessionStart and UserPrompt hooks.
- Worker frontmatter (between the opening `---` markers) supports a `worker-identity` block; the hooks parse this to surface `preferred_name`, `mailbox`, and `register_with_agent_mail` as a reminder every session. Parsed values are written to `.claude/sessions/<session-id>/current_worker_identity.json` and exported as environment variables: `CLAUDE_AGENT_MAILBOX`, `CLAUDE_WORKER_TEMP_PREFIX`, and `CLAUDE_WORKER_REGISTER_WITH_MAIL`.
- Use the temp prefix when creating Agent Mail helper files (for example `tmp_agentmail_${CLAUDE_WORKER_TEMP_PREFIX}_register.json`). Hooks automatically remove files that match `tmp_agentmail_${CLAUDE_WORKER_TEMP_PREFIX}_*.json`, `tmp_worker_${CLAUDE_WORKER_TEMP_PREFIX}_*.json`, and `tmp_${CLAUDE_WORKER_TEMP_PREFIX}_*.json` at session start and end within the current session directory.
- Workers flagged with `register_with_agent_mail: true` are registered with Agent Mail at session start and their inbox is fetched. Configure the target project via `CLAUDE_AGENT_MAIL_PROJECT_KEY` (default `/project`). Use the MCP Agent Mail `fetch_inbox` tool to check for new messages, and run `./.claude/hooks/ack-worker-mail-alert.sh` after processing.
- Top-level `tools:` entries in the frontmatter are now enforced. List the exact tool names you want the worker to use (e.g. `Read, Write, Edit, Task, TodoWrite, Bash, Grep, Glob, WebSearch`). Any other tool call will be blocked with a `<tool-permission-denied>` warning until you update the worker file. Leave the field empty to allow all tools.
- Adding `uses_beads: true` tells the hooks to run `bd quickstart` and `bd ready --json` on every session start (output stored in `.claude/beads/quickstart.log`, with the tail displayed in the worker banner). The Beads CLI (`bd`) must be installed and on `PATH`.
- When `uses_beads: true` workers call `./.claude/hooks/log-discovery.sh bug "..."`, the hook automatically runs `bd create` (type `bug`, priority 1, labels `bug,auto`) to capture it in the Beads backlog and logs the result to `.claude/beads/bug-issues.log`.

#### Launching Workers on Each Platform

**Interactive Selection (Recommended)**

The easiest way to launch workers is with the interactive selector - just run it and pick from a menu:

```bash
# PowerShell (Windows)
.\.claude\scripts\select-worker.ps1

# Bash (macOS/Linux/WSL/Git Bash)
bash .claude/scripts/select-worker.sh
```

This shows a numbered menu of available workers, auto-generates a unique session ID, and launches Claude with the correct environment variables.

**Quick Selection**

You can also pass a worker name or number directly:

```bash
# By partial name (matches first worker containing "backend")
.\.claude\scripts\select-worker.ps1 backend

# By number (from the menu order)
bash .claude/scripts/select-worker.sh 2

# List available workers without launching
.\.claude\scripts\select-worker.ps1 -List
```

**Add to PowerShell Profile (Optional)**

For quick access, add this function to your `$PROFILE`:

```powershell
function cw { & "$PWD\.claude\scripts\select-worker.ps1" @args }
```

Then just type `cw` to launch the interactive menu.

**Manual Methods**

- **macOS/Linux/Git Bash/WSL**: `CLAUDE_SESSION_ID=pm-1 CLAUDE_WORKER_PROFILE=project-manager claude`
- **PowerShell helper**: `pwsh -NoLogo -File .claude/scripts/run-worker.ps1 project-manager pm-1` (auto-sets `WSLENV` so hooks receive the variables)
- **PowerShell (manual export)**:
  1. Run `setx WSLENV "CLAUDE_WORKER_PROFILE/u:CLAUDE_SESSION_ID/u:CLAUDE_AGENT_MAIL_PROJECT_KEY/u"` once (new terminal required). For a single session use `$env:WSLENV='CLAUDE_WORKER_PROFILE/u:CLAUDE_SESSION_ID/u:CLAUDE_AGENT_MAIL_PROJECT_KEY/u'`.
  2. Then: `$env:CLAUDE_SESSION_ID='pm-1'; $env:CLAUDE_WORKER_PROFILE='project-manager'; claude`
- **Command Prompt**: `set CLAUDE_SESSION_ID=pm-1 && set CLAUDE_WORKER_PROFILE=project-manager && claude`
- **One-liner helper**: `bash .claude/scripts/run-worker.sh project-manager pm-1` (generates a unique session id automatically if you skip the second argument).

Parallel sessions all share `.claude/capsule.toon` and `.claude/shared/`, but their per-window logs (tasks, file access, Agent Mail alerts) live under `.claude/sessions/<session-id>/`.

### Parallel Sessions

- Session-scoped runtime state (worker identity cache, file/task logs, Agent Mail alerts, capsule hash, etc.) lives under `.claude/sessions/<CLAUDE_SESSION_ID>/`.
- Set `CLAUDE_SESSION_ID` manually (e.g., `CLAUDE_SESSION_ID=pm-1 CLAUDE_WORKER_PROFILE=project-manager claude`) or run `bash .claude/scripts/run-worker.sh <profile> [session-id]` to generate a unique id per window.
- Shared resources such as `.claude/capsule.toon` and `.claude/shared/` remain global, so the capsule still aggregates across workers.

### Hive Memory Storage

- Shared JSONL logs live in `.claude/shared/` (`file_access.log`, `tasks.log`, `discoveries.log`). Hooks take file locks before appending.
- `prune-shared-logs.sh` keeps only the latest 48 hours of entries, so the team capsule stays fresh without manual cleanup.
- Per-session logs under `.claude/` continue to exist, but the capsule prioritizes the shared logs so every worker sees the same context.
- Each window’s scratch data (worker caches, recent file/task logs, Agent Mail alerts, etc.) now sits under `.claude/sessions/<CLAUDE_SESSION_ID>/`. Delete a specific session directory to reset a single worker without affecting others.

### Customization

- **Custom hooks** - Add to `hooks/` directory
- **Custom tools** - Add to `tools/` directory
- **Specialized agents** - Add to `agents/` directory
- **Reusable skills** - Add to `skills/` directory

See [Configuration Guide](docs/CONFIGURATION.md) for details.

---

## Troubleshooting

### Hooks not executing

```bash
# Verify settings
cat .claude/settings.local.json

# Test hook manually
bash .claude/hooks/session-start.sh
```

### Capsule not updating

```bash
# Force refresh
rm .claude/last_refresh_state.txt

# Check logs
tail -f .claude/hooks.log
```

### Dependency graph not building

```bash
# Verify scanner installation
ls -la ~/.claude/bin/dependency-scanner

# Rebuild manually
~/.claude/bin/dependency-scanner --path . --output .claude/dep-graph.toon
```

### Debug Mode

Enable verbose logging:

```bash
CLAUDE_DEBUG_HOOKS=true claude
```

For more issues, see [FAQ](docs/FAQ.md) or [open an issue](https://github.com/arpitnath/super-claude-kit/issues).

---

## Performance

### Benchmarks

| Operation | Performance | Details |
|-----------|-------------|---------|
| **Context Refresh** | <100ms | Smart change detection |
| **Graph Building** | 1000 files in <5s | Parallel parsing |
| **Large Project** | 10000 files in <30s | Incremental updates |
| **Token Efficiency** | ~52% reduction | TOON vs JSON and avoids re-reads |

---

## Uninstall

```bash
cd super-claude-kit
bash uninstall
```

Removes hooks, tools, and configuration. Your `.claude/` data logs are preserved in `.claude/backup/`.

---

## Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes with clear messages
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

### Development Setup

```bash
git clone https://github.com/arpitnath/super-claude-kit.git
cd super-claude-kit
bash install
```

### Running Tests

```bash
bash .claude/scripts/test-super-claude.sh
```

---

## License

This repository is licensed under the [MIT License](LICENSE).

Copyright (c) 2025 Arpit Nath

---

## Acknowledgments

- [Anthropic](https://www.anthropic.com/) - Claude and Claude Code
- [TOON Format](https://github.com/toon-format/toon) - Token-Oriented Object Notation
- [Tree-sitter](https://tree-sitter.github.io/) - Incremental parsing system

---

## Star History

If you found Super Claude Kit useful, please star the repo! ⭐

<p align="center">
  <a href="https://star-history.com/#arpitnath/super-claude-kit&Date">
    <img src="https://api.star-history.com/svg?repos=arpitnath/super-claude-kit&type=Date" alt="Star History Chart" width="600">
  </a>
</p>

---

<p align="center">
  <strong>Never re-explain yourself to Claude. Ever.</strong>
  <br/>
  <br/>
  <a href="https://github.com/arpitnath/super-claude-kit/issues">Report Bug</a> ·
  <a href="https://github.com/arpitnath/super-claude-kit/issues">Request Feature</a> ·
  <a href="https://github.com/arpitnath">GitHub</a> ·
  <a href="https://www.linkedin.com/in/arpit-nath-38280a173/">LinkedIn</a>
</p>

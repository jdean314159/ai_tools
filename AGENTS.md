# ai_tools agent instructions

## Project orientation

Treat `docs/design/VISION.md` as the canonical architecture and handoff
document. For current implementation status, use `docs/internal/STATUS.md`;
the older `CURRENT_STATE.md` name has been consolidated into `STATUS.md`.
Before making architectural changes, read:
- `docs/design/VISION.md`
- `docs/internal/STATUS.md`
- `docs/internal/ROADMAP.md`
- `docs/learning/START_HERE.md`
- relevant package README files

## Change policy

Prefer small, reviewable patches.
Do not perform broad rewrites unless explicitly requested.
Do not move packages, rename public APIs, or change import topology without first explaining the rationale.
Preserve compatibility with editable installs and monorepo-style local development.

## Testing policy

Prefer targeted tests first, then broader tests.
Use these environment conventions when applicable:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
    PYTHONDONTWRITEBYTECODE=1

Do not claim tests passed unless they were actually run.
If a test cannot be run, state the exact reason.

## Python style

Prefer package-scoped imports over path hacks.
Avoid duplicate contract definitions.
Keep modules simple and boring unless complexity is justified.
Favor explicit adapters and stable protocols at package boundaries.

## Safety

Do not edit files outside this repository.
Do not delete user data, model files, virtual environments, or local databases unless explicitly instructed.
Do not run networked installs, destructive shell commands, or Git history rewrites without explicit approval.

## Response format

For code changes, summarize:
- files changed
- why they changed
- tests run
- remaining risks

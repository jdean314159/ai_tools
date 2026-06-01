#!/bin/bash

# Quality Check Hook
# Post-response validation to ensure optimal approach was used
# Runs AFTER Claude responds but BEFORE sending to user
#
# IMPORTANT: This hook must NOT output to stdout - it corrupts Claude Code UI.
# For PostToolUse/PreToolUse hooks, only valid JSON or nothing should be output.
# Diagnostic output goes to stderr only.

# Redirect all output to stderr for debugging (not shown in normal mode)
exec 2>>.claude/hook-errors.log

# This hook is informational only - no stdout output needed
# If you want to enable quality check logging, uncomment below:
# {
#   echo "QUALITY CHECK: Parallel calls, delegation, memory, progress, discoveries, redundancy"
# } >> "${CLAUDE_SESSION_DIR:-/tmp}/quality_check.log" 2>/dev/null

# Always continue (silent - no stdout output to avoid UI corruption)
exit 0

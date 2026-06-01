#!/bin/bash

# Update Capsule - Build capsule.toon from session and shared hive data
# Uses TOON format (Token-Oriented Object Notation) for 52% token savings

WORKER_PROFILE="${CLAUDE_WORKER_PROFILE:-default}"
SESSION_ID="${CLAUDE_SESSION_ID:-$WORKER_PROFILE}"
SESSION_DIR=".claude/sessions/$SESSION_ID"
SHARED_DIR=".claude/shared"
CAPSULE_FILE="$SESSION_DIR/capsule.toon"

mkdir -p "$SESSION_DIR" 2>/dev/null

# Export variables for Python
export SESSION_DIR
export SHARED_DIR
export WORKER_PROFILE
export CAPSULE_FILE

# Build capsule using Python for safe JSON handling
python3 << 'PYTHON_SCRIPT'
import json
import os
import subprocess
from datetime import datetime
from collections import defaultdict

session_dir = os.environ.get('SESSION_DIR', '.claude/sessions/default')
shared_dir = os.environ.get('SHARED_DIR', '.claude/shared')
worker_profile = os.environ.get('WORKER_PROFILE', 'default')
capsule_file = os.environ.get('CAPSULE_FILE', f'{session_dir}/capsule.toon')

def read_jsonl(filepath):
    """Read JSONL file, return list of dicts"""
    entries = []
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except:
                            pass
        except:
            pass
    return entries

def get_git_state():
    """Get current git state"""
    try:
        branch = subprocess.run(['git', 'branch', '--show-current'],
                              capture_output=True, text=True, timeout=5).stdout.strip()
        status = subprocess.run(['git', 'status', '--porcelain'],
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return {'branch': branch, 'changes': len(status.split('\n')) if status else 0}
    except:
        return {'branch': 'unknown', 'changes': 0}

# Gather data
git_state = get_git_state()

# Session file access (this worker only)
session_files = read_jsonl(f'{session_dir}/file_access.log')

# Shared file access (all workers, last 48h)
shared_files = read_jsonl(f'{shared_dir}/file_access.log')

# Session discoveries
session_discoveries = read_jsonl(f'{session_dir}/discoveries.log')

# Shared discoveries (all workers)
shared_discoveries = read_jsonl(f'{shared_dir}/discoveries.log')

# Session tasks
session_tasks = read_jsonl(f'{session_dir}/tasks.log')

# Shared tasks (all workers)
shared_tasks = read_jsonl(f'{shared_dir}/tasks.log')

# Build TOON format (compact, token-efficient)
toon_lines = []
toon_lines.append(f"#capsule v1")
toon_lines.append(f"@meta profile={worker_profile} ts={int(datetime.now().timestamp())}")

# Git state
toon_lines.append(f"@git branch={git_state['branch']} changes={git_state['changes']}")

# Files in context (deduplicated, most recent action)
files_seen = {}
for entry in session_files + shared_files:
    path = entry.get('path', '')
    if path:
        profile = entry.get('profile', worker_profile)
        action = entry.get('action', 'read')
        ts = entry.get('timestamp', 0)
        key = path
        if key not in files_seen or ts > files_seen[key]['ts']:
            files_seen[key] = {'profile': profile, 'action': action, 'ts': ts}

toon_lines.append(f"@files count={len(files_seen)}")
for path, info in sorted(files_seen.items(), key=lambda x: -x[1]['ts'])[:50]:  # Top 50 most recent
    toon_lines.append(f"  {info['action'][0]}:{info['profile']}:{path}")

# Discoveries (deduplicated)
discoveries_seen = {}
for entry in session_discoveries + shared_discoveries:
    desc = entry.get('description', '')
    if desc:
        cat = entry.get('category', 'insight')
        profile = entry.get('profile', worker_profile)
        ts = entry.get('timestamp', 0)
        key = desc[:100]  # Dedupe by first 100 chars
        if key not in discoveries_seen or ts > discoveries_seen[key]['ts']:
            discoveries_seen[key] = {'category': cat, 'profile': profile, 'description': desc, 'ts': ts}

toon_lines.append(f"@discoveries count={len(discoveries_seen)}")
for key, info in sorted(discoveries_seen.items(), key=lambda x: -x[1]['ts'])[:30]:  # Top 30
    toon_lines.append(f"  {info['category'][0]}:{info['profile']}:{info['description'][:200]}")

# Tasks (latest status per task)
tasks_seen = {}
for entry in session_tasks + shared_tasks:
    content = entry.get('content', '')
    if content:
        status = entry.get('status', 'pending')
        profile = entry.get('profile', worker_profile)
        ts = entry.get('timestamp', 0)
        key = content[:100]
        if key not in tasks_seen or ts > tasks_seen[key]['ts']:
            tasks_seen[key] = {'status': status, 'profile': profile, 'content': content, 'ts': ts}

toon_lines.append(f"@tasks count={len(tasks_seen)}")
for key, info in sorted(tasks_seen.items(), key=lambda x: -x[1]['ts'])[:30]:  # Top 30
    status_char = {'pending': 'P', 'in_progress': 'I', 'completed': 'C'}.get(info['status'], 'P')
    toon_lines.append(f"  {status_char}:{info['profile']}:{info['content'][:200]}")

# Write capsule
with open(capsule_file, 'w') as f:
    f.write('\n'.join(toon_lines))

# Output hash for change detection
import hashlib
content = '\n'.join(toon_lines)
print(hashlib.md5(content.encode()).hexdigest())
PYTHON_SCRIPT

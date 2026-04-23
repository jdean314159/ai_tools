#!/bin/bash
# update_engram.sh — push local Engram changes to GitHub
# Usage: ./update_engram.sh "commit message"

set -e

REPO_DIR=~/ai_tools/engram
MSG="${1:-v0.1.19.1: bug fixes}"

cd "$REPO_DIR"

git add -A
git status
git commit -m "$MSG"
git push origin main

echo "Done."



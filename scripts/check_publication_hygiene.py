#!/usr/bin/env python3
"""Validate publication hygiene for the ai_tools monorepo."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_ROOT_DOCS = [
    'README.md',
    'START_HERE.md',
    'VISION.md',
    'CURRENT_STATE.md',
    'ROADMAP.md',
    'ADR_INDEX.md',
    'LEARNING_PATH.md',
    'GITHUB_PUBLICATION_CHECKLIST.md',
]

LEGACY_BASENAMES = {
    'README_engram_lite.legacy.md',
    'README_llm_inspector.legacy.md',
    'README_llm_inspector_ui.legacy.md',
}


def main() -> int:
    problems: list[str] = []

    for rel in REQUIRED_ROOT_DOCS:
        if not (ROOT / rel).exists():
            problems.append(f'missing required root document: {rel}')

    pycache_dirs = sorted(p.relative_to(ROOT) for p in ROOT.rglob('__pycache__'))
    pyc_files = sorted(p.relative_to(ROOT) for p in ROOT.rglob('*.pyc'))
    pyo_files = sorted(p.relative_to(ROOT) for p in ROOT.rglob('*.pyo'))

    if pycache_dirs:
        preview = ', '.join(str(p) for p in pycache_dirs[:10])
        extra = '' if len(pycache_dirs) <= 10 else f' ... (+{len(pycache_dirs) - 10} more)'
        problems.append(f'found __pycache__ directories: {preview}{extra}')
    if pyc_files:
        preview = ', '.join(str(p) for p in pyc_files[:10])
        extra = '' if len(pyc_files) <= 10 else f' ... (+{len(pyc_files) - 10} more)'
        problems.append(f'found .pyc files: {preview}{extra}')
    if pyo_files:
        preview = ', '.join(str(p) for p in pyo_files[:10])
        extra = '' if len(pyo_files) <= 10 else f' ... (+{len(pyo_files) - 10} more)'
        problems.append(f'found .pyo files: {preview}{extra}')

    misplaced_legacy = []
    for path in ROOT.rglob('*.md'):
        if path.name in LEGACY_BASENAMES and 'docs/history' not in str(path.parent):
            misplaced_legacy.append(path.relative_to(ROOT))
    if misplaced_legacy:
        problems.append(
            'legacy package READMEs should live under docs/history/: '
            + ', '.join(str(p) for p in misplaced_legacy)
        )

    if problems:
        print('Publication hygiene check failed:')
        for problem in problems:
            print(f'- {problem}')
        return 1

    print('Publication hygiene check passed.')
    print('Required root docs present:', ', '.join(REQUIRED_ROOT_DOCS))
    print('No __pycache__/ or compiled Python artifacts found.')
    print('Legacy package READMEs are confined to docs/history/.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

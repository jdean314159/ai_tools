from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
MIN_NOTEBOOKS = 6
MIN_STARTER_PROJECTS = 3

ROOT_ENTRY_DOCS = [
    ROOT / 'START_HERE.md',
    ROOT / 'LEARNING_PATH.md',
]

REFERENCE_GUIDES = [
    ROOT / 'language_tutor' / 'REFERENCE_APP_GUIDE.md',
    ROOT / 'llm_inspector_ui' / 'WORKBENCH_TEACHING_GUIDE.md',
    ROOT / 'llm_harness_core' / 'EVALUATION_WALKTHROUGH.md',
]

REQUIRED_NOTEBOOKS = [
    ROOT / 'course' / 'notebooks' / '00_llm_fundamentals.ipynb',
    ROOT / 'course' / 'notebooks' / '01_environment_setup.ipynb',
    ROOT / 'course' / 'notebooks' / '02_engine_basics.ipynb',
    ROOT / 'course' / 'notebooks' / '03_inspecting_model_behavior.ipynb',
    ROOT / 'course' / 'notebooks' / '04_memory_with_engram_lite.ipynb',
    ROOT / 'course' / 'notebooks' / '05_rag_with_rag_lib.ipynb',
    ROOT / 'course' / 'notebooks' / '06_advanced_rag_and_evaluation.ipynb',
    ROOT / 'course' / 'notebooks' / '07_reference_app_walkthrough.ipynb',
    ROOT / 'course' / 'notebooks' / '08_agent_safety_and_failure_modes.ipynb',
    ROOT / 'course' / 'notebooks' / '09_evaluating_llm_applications.ipynb',
]

TUTORIALS = [
    ROOT / 'docs' / 'tutorials' / 'broken_rag_lab.md',
    ROOT / 'docs' / 'tutorials' / 'memory_contamination_lab.md',
    ROOT / 'docs' / 'tutorials' / 'agent_red_team_lab.md',
]

EXAMPLE_COMMAND_SPECS = [
    {"cmd": [sys.executable, str(ROOT / 'rag_lib' / 'examples' / 'broken_rag_lab.py')], "expect": 'Evaluation summary'},
    {"cmd": [sys.executable, str(ROOT / 'engram' / 'examples' / 'memory_contamination_lab.py')], "expect": '=== Scenario:'},
    {"cmd": [sys.executable, str(ROOT / 'agent_lib' / 'examples' / 'agent_red_team_lab.py')], "expect": '=== Scenario:'},
    {"cmd": [sys.executable, str(ROOT / 'course' / 'starter_projects' / 'source_grounded_qa' / 'eval.py')], "expect": 'Evaluation summary'},
]

PYTHONPATH = ':'.join([
    str(ROOT / 'rag_lib' / 'src'),
    str(ROOT / 'engram'),
    str(ROOT / 'engram_lite' / 'src'),
    str(ROOT / 'llm_inspector' / 'src'),
    str(ROOT / 'llm_harness_core' / 'src'),
    str(ROOT / 'agent_lib' / 'src'),
    str(ROOT / 'llm_engines'),
    str(ROOT),
])


def extract_python_example_paths(markdown: str) -> list[str]:
    pattern = re.compile(r"python\s+([^\n`]+\.py)")
    return pattern.findall(markdown)


def iter_notebooks() -> Iterable[Path]:
    for base in [ROOT / 'course' / 'notebooks', ROOT / 'notebooks']:
        if base.exists():
            yield from sorted(base.rglob('*.ipynb'))


def iter_starter_projects() -> Iterable[Path]:
    for base in [ROOT / 'course' / 'starter_projects', ROOT / 'starter_projects']:
        if base.exists():
            for child in sorted(base.iterdir()):
                if child.is_dir():
                    yield child


def _run_command(cmd: list[str], *, expect: str | None = None, timeout_seconds: int = 30) -> None:
    env = dict(os.environ)
    env['PYTHONPATH'] = PYTHONPATH
    env.setdefault('AI_TOOLS_LIGHTWEIGHT', '1')
    env.setdefault('PYTHONDONTWRITEBYTECODE', '1')
    try:
        proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(
            f"Command timed out after {timeout_seconds}s: {' '.join(cmd)}\nSTDOUT:\n{exc.stdout or ''}\nSTDERR:\n{exc.stderr or ''}"
        ) from exc
    if proc.returncode != 0:
        raise AssertionError(
            f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    if expect and expect not in proc.stdout:
        raise AssertionError(
            f"Command did not print expected marker {expect!r}: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}"
        )


def validate_root_entry_docs() -> None:
    for doc in ROOT_ENTRY_DOCS:
        if not doc.exists():
            raise AssertionError(f'Missing root teaching entry document: {doc}')
        text = doc.read_text(encoding='utf-8').strip()
        if not text:
            raise AssertionError(f'Root teaching entry document is empty: {doc}')
        if doc.name == "START_HERE.md" and "What you can ignore for now" not in text:
            raise AssertionError(f'START_HERE.md is missing the ignore-for-now guidance: {doc}')


def validate_reference_guides() -> None:
    for guide in REFERENCE_GUIDES:
        if not guide.exists():
            raise AssertionError(f'Missing reference guide: {guide}')
        text = guide.read_text(encoding='utf-8').strip()
        if not text:
            raise AssertionError(f'Reference guide is empty: {guide}')
        if guide.name == "REFERENCE_APP_GUIDE.md":
            if "Stage 5" not in text or "llm_engines" not in text:
                raise AssertionError(f'Reference guide missing expected teaching markers: {guide}')
        elif guide.name == "WORKBENCH_TEACHING_GUIDE.md":
            if "Stage 2" not in text or "Compare panel" not in text:
                raise AssertionError(f'Workbench guide missing expected teaching markers: {guide}')
        elif guide.name == "EVALUATION_WALKTHROUGH.md":
            if "baseline" not in text.lower() or "augmented" not in text.lower():
                raise AssertionError(f'Evaluation walkthrough missing expected teaching markers: {guide}')


def validate_required_notebooks() -> None:
    for notebook in REQUIRED_NOTEBOOKS:
        if not notebook.exists():
            raise AssertionError(f'Missing required notebook: {notebook}')


def validate_tutorial_links() -> None:
    for tutorial in TUTORIALS:
        text = tutorial.read_text(encoding='utf-8')
        paths = extract_python_example_paths(text)
        if not paths:
            raise AssertionError(f'No runnable python example path found in {tutorial}')
        for rel in paths:
            target = ROOT / rel.strip()
            if not target.exists():
                raise AssertionError(f'Tutorial {tutorial} references missing file: {rel}')


def run_examples() -> None:
    for spec in EXAMPLE_COMMAND_SPECS:
        cmd = list(spec['cmd'])
        expect = spec.get('expect')
        print(f"Checking runnable example: {' '.join(cmd)}", flush=True)
        _run_command(cmd, expect=expect)
        print(f"OK: {' '.join(cmd)}", flush=True)


def validate_notebooks() -> int:
    count = 0
    for notebook in iter_notebooks():
        count += 1
        data = json.loads(notebook.read_text(encoding='utf-8'))
        if data.get('nbformat') is None:
            raise AssertionError(f'Notebook missing nbformat: {notebook}')
        cells = data.get('cells')
        if not isinstance(cells, list) or not cells:
            raise AssertionError(f'Notebook has no cells: {notebook}')
        if not any(
            cell.get('cell_type') in {'code', 'markdown'}
            for cell in cells
            if isinstance(cell, dict)
        ):
            raise AssertionError(f'Notebook has no usable cells: {notebook}')
    return count


def validate_starter_projects() -> int:
    count = 0
    for project in iter_starter_projects():
        count += 1
        readme = project / 'README.md'
        if readme.exists() and not readme.read_text(encoding='utf-8').strip():
            raise AssertionError(f'Starter project README is empty: {readme}')

        py_files = sorted(project.glob('*.py'))
        if not py_files:
            raise AssertionError(f'Starter project has no Python files: {project}')

        for target in py_files:
            try:
                ast.parse(target.read_text(encoding='utf-8'), filename=str(target))
            except SyntaxError as exc:
                raise AssertionError(f'Starter project file has invalid syntax: {target}\n{exc}') from exc

        eval_target = project / 'eval.py'
        if eval_target.exists():
            _run_command([sys.executable, str(eval_target)], expect='Evaluation summary')
    return count


def main() -> int:
    print('Validating root teaching entry docs', flush=True)
    validate_root_entry_docs()
    print('Validating reference guides', flush=True)
    validate_reference_guides()
    print('Validating required notebooks', flush=True)
    validate_required_notebooks()
    print('Validating tutorial links', flush=True)
    validate_tutorial_links()
    print('Running teaching examples', flush=True)
    run_examples()
    print('Validating notebooks', flush=True)
    notebook_count = validate_notebooks()
    print('Validating starter projects', flush=True)
    starter_count = validate_starter_projects()
    if notebook_count < MIN_NOTEBOOKS:
        raise AssertionError(f'Expected at least {MIN_NOTEBOOKS} notebooks, found {notebook_count}')
    if starter_count < MIN_STARTER_PROJECTS:
        raise AssertionError(f'Expected at least {MIN_STARTER_PROJECTS} starter projects, found {starter_count}')
    print('Teaching artifacts OK')
    print(f'Notebook count: {notebook_count}')
    print(f'Starter project count: {starter_count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

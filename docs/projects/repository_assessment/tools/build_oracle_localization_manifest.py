"""Build frozen inputs for the Ornith oracle-localization A/B/C test."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUT = (
    ROOT
    / "docs/projects/repository_assessment/runs/2026-09-10-ornith-oracle-localization-abc"
)
SEEDS = (17, 31, 47)

# Every negative is the corrected-reference counterpart of the target defect.
# Those references pass the external graders recorded in TARGET-ACQUISITION-2026-09-08.md.
PAIR_SPECS: tuple[dict[str, Any], ...] = (
    {
        "pair_id": "tool_state",
        "path": "agent_lib/src/agent_lib/interop.py",
        "defect": ("23c1549d5aae3ac67454aade1b725f2931770014", 22, 58),
        "negative": ("49026eac3d2e24b02641bf9db0a76e94909e9386", 22, 58),
        "hypothesis": (
            "The helper fails to classify a tool_not_granted error as blocked policy "
            "execution, so downstream warnings misclassify the result."
        ),
        "oracle": (
            "tool_not_granted is omitted from the blocked-policy error set and is therefore "
            "not classified as blocked."
        ),
        "match_groups": (
            (r"tool[_ -]?not[_ -]?granted", r"ungranted"),
            (r"block", r"policy"),
            (r"omit", r"missing", r"not (?:classif|treat|includ|mark)", r"fail"),
        ),
    },
    {
        "pair_id": "git_fail_closed",
        "path": "scripts/check_publication_hygiene.py",
        "defect": ("23c1549d5aae3ac67454aade1b725f2931770014", 17, 35),
        "negative": ("49026eac3d2e24b02641bf9db0a76e94909e9386", 19, 40),
        "hypothesis": (
            "The tracked-file inventory helper does not fail closed when git is unavailable or "
            "returns an error, so an empty inventory can silently pass publication checks."
        ),
        "oracle": (
            "git ls-files failures are unchecked; stderr and return code are ignored and empty "
            "stdout is treated as a valid tracked-file inventory."
        ),
        "match_groups": (
            (r"git", r"ls.files", r"tracked.file"),
            (r"return.?code", r"exit status", r"unavailable", r"fail", r"error"),
            (r"fail.closed", r"silent", r"empty", r"unchecked", r"ignor", r"pass"),
        ),
    },
    {
        "pair_id": "storage_path_escape",
        "path": "engram/src/engram/project_memory.py",
        "defect": ("7d37920a81a9cb672c24af3a55557621e5c5009f", 305, 315),
        "negative": ("8e2e9e5f2c45c935bdc3afa2479a08dc702b44db", 311, 327),
        "hypothesis": (
            "The project identifier is used as a path component without validation, allowing "
            "separators or traversal values to escape the configured storage root."
        ),
        "oracle": (
            "project_id is joined directly to base_dir without requiring a single safe path "
            "component, allowing path traversal."
        ),
        "match_groups": (
            (r"project.?id", r"identifier"),
            (r"path", r"travers", r"separator", r"component", r"escape"),
            (r"validat", r"saniti", r"reject", r"unchecked", r"without"),
        ),
    },
    {
        "pair_id": "storage_permissions",
        "path": "engram/src/engram/project_memory.py",
        "defect": ("7d37920a81a9cb672c24af3a55557621e5c5009f", 317, 352),
        "negative": ("8e2e9e5f2c45c935bdc3afa2479a08dc702b44db", 329, 381),
        "hypothesis": (
            "Persistent memory directories and JSONL files are created without enforcing private "
            "0700 and 0600 modes, so a permissive umask can expose stored memory."
        ),
        "oracle": (
            "storage directories and JSONL files inherit the process umask instead of enforcing "
            "private directory and file modes."
        ),
        "match_groups": (
            (r"permission", r"mode", r"umask", r"chmod", r"0700", r"0600"),
            (r"director", r"file", r"jsonl", r"storage", r"memory"),
            (r"private", r"expos", r"permissive", r"not enforc", r"inherit"),
        ),
    },
    {
        "pair_id": "cross_tenant_delete",
        "path": "engram/src/engram/project_memory.py",
        "defect": ("7d37920a81a9cb672c24af3a55557621e5c5009f", 1990, 2018),
        "negative": ("8e2e9e5f2c45c935bdc3afa2479a08dc702b44db", 2035, 2076),
        "hypothesis": (
            "delete_episode removes an episode without applying configured tenant authorization, "
            "allowing a caller to delete another tenant's episode."
        ),
        "oracle": (
            "delete_episode deletes a matching episode without consulting MemoryTrustPolicy tenant "
            "authorization."
        ),
        "match_groups": (
            (r"delet", r"remov"),
            (r"tenant", r"trust.?policy"),
            (r"authoriz", r"cross.tenant", r"mismatch", r"ownership", r"without"),
        ),
    },
)

SYSTEM_PROMPT = """You are reviewing one isolated source span. Judge only behavior supported by the shown code. Do not assume unseen repository context. Return only the requested JSON object."""

B_USER_TEMPLATE = """Review this isolated source span for a concrete correctness, security, or reliability violation. If the span supports one, identify the affected behavior and state the actionable violation. If it does not, return no_violation and explain why the shown behavior is acceptable.

Source: {path}, lines {start_line}-{end_line}
```{language}
{text}```"""

C_USER_TEMPLATE = """Evaluate the hypothesis against this isolated source span. Confirm it only if the shown code supports the claimed behavior and actionable violation; otherwise reject it. Do not infer missing surrounding behavior.

Hypothesis: {hypothesis}

Source: {path}, lines {start_line}-{end_line}
```{language}
{text}```"""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _show(commit: str, path: str) -> list[str]:
    data = subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT, text=True)
    return data.splitlines()


def _span(commit: str, path: str, start: int, end: int) -> dict[str, Any]:
    lines = _show(commit, path)
    if not 1 <= start <= end <= len(lines):
        raise ValueError(f"invalid span {commit}:{path}:{start}-{end}")
    text = "\n".join(lines[start - 1 : end]) + "\n"
    return {
        "commit": commit,
        "path": path,
        "start_line": start,
        "end_line": end,
        "line_count": end - start + 1,
        "sha256": _sha256(text.encode()),
        "text": text,
    }


def build_payloads() -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    oracles: list[dict[str, Any]] = []
    for spec in PAIR_SPECS:
        pair_id = spec["pair_id"]
        for kind in ("defect", "negative"):
            commit, start, end = spec[kind]
            items.append(
                {
                    "item_id": f"{kind}_{pair_id}",
                    "pair_id": pair_id,
                    "kind": kind,
                    **_span(commit, spec["path"], start, end),
                }
            )
        oracles.append(
            {
                "pair_id": pair_id,
                "hypothesis": spec["hypothesis"],
                "oracle": spec["oracle"],
                "match_groups": [list(group) for group in spec["match_groups"]],
            }
        )

    item_by_id = {row["item_id"]: row for row in items}
    b_order = [
        "defect_tool_state",
        "negative_git_fail_closed",
        "defect_storage_path_escape",
        "negative_storage_permissions",
        "defect_cross_tenant_delete",
        "negative_tool_state",
        "defect_git_fail_closed",
        "negative_storage_path_escape",
        "defect_storage_permissions",
        "negative_cross_tenant_delete",
    ]
    matrix: list[dict[str, Any]] = []
    order = 0
    for condition, item_order in (("B", b_order), ("C", list(reversed(b_order)))):
        for item_offset, item_id in enumerate(item_order):
            for seed_offset in range(len(SEEDS)):
                seed = SEEDS[(item_offset + seed_offset) % len(SEEDS)]
                item = item_by_id[item_id]
                order += 1
                truth = "defect" if item["kind"] == "defect" else "negative"
                if condition == "C":
                    truth = "true_hypothesis" if item["kind"] == "defect" else "false_hypothesis"
                matrix.append(
                    {
                        "order": order,
                        "run_id": f"{order:02d}-{condition.lower()}-{item_id}-seed{seed}",
                        "condition": condition,
                        "item_id": item_id,
                        "pair_id": item["pair_id"],
                        "truth": truth,
                        "seed": seed,
                    }
                )

    return {
        "span-manifest.json": {
            "schema": "oracle-localization-span-manifest/v2",
            "pre_generation_correction": (
                "Supersedes v1 at commit 6eff393 before model generation: the later-added private "
                "endpoint was not a target defect, the permissions defect was omitted, and the "
                "path-escape span did not contain the faulty join."
            ),
            "items": items,
        },
        "oracle-manifest.json": {
            "schema": "oracle-localization-oracle-manifest/v1",
            "grader_boundary": "evaluator-only except each condition-C item's hypothesis",
            "oracles": oracles,
        },
        "prompts.json": {
            "schema": "oracle-localization-prompts/v1",
            "system": SYSTEM_PROMPT,
            "condition_b_user_template": B_USER_TEMPLATE,
            "condition_c_user_template": C_USER_TEMPLATE,
        },
        "run-matrix.json": {
            "schema": "oracle-localization-run-matrix/v1",
            "model": "Ornith-1.5-35B-Q4_K_M.gguf",
            "temperature": 0,
            "thinking": False,
            "max_tokens": 512,
            "seeds": list(SEEDS),
            "runs": matrix,
        },
    }


def write_payloads(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in build_payloads().items():
        (output_dir / filename).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    write_payloads(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

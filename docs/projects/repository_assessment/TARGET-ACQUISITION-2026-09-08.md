# Repository-assessment target acquisition — 2026-09-08

Status: two model-blind candidate targets validated; independent Phase 2 target
gate not satisfied.

## Outcome

Two recent historical trees each expose exactly three externally gradable
defects and retain the same nine package scopes used by the staged-v1 and
adaptive-v2.2 harnesses. Each grader fails 3/3 on its target and passes 3/3 on
its specific corrected reference.

These are usable for an explicitly exploratory transfer study. They are not
independently prepared blinded-confirmation targets: Codex selected the commits
and wrote the graders after inspecting the later fixes. The model has not seen
the defect identities, grader source, fix messages, or corrected trees, but the
harness author has. No Phase 2 run is authorized by this record.

## Selected candidate targets

| Target | Target tree | Target tar SHA-256 | Corrected reference | Reference tree | Reference tar SHA-256 | Grader outcome |
| --- | --- | --- | --- | --- | --- | --- |
| `23c1549d5aae3ac67454aade1b725f2931770014` | `d4faa7c547ab8e34f251124c7e5ca7a9dcbf6364` | `ba24146927228771ccefc078cf8732e0a1abb77e3d4a77ff699205742413d1b0` | `49026eac3d2e24b02641bf9db0a76e94909e9386` | `a55d073413f0f5d83a711d9e5a59e1d85040c6ca` | `4fba9a6ddfb60f2f1ce6062e92f4fafb0f5b2cc3e02640e121b47827249ec6b2` | target 0/3 pass; reference 3/3 pass |
| `7d37920a81a9cb672c24af3a55557621e5c5009f` | `0177f7c8288a42ca771084c42362ddb6f90a9640` | `02e68e5c7cb349f1c6e3011fd6f0265ebdf6a87fa753bef932fabfd271bd8769` | `8e2e9e5f2c45c935bdc3afa2479a08dc702b44db` | `1bfc4d68cf322489cda7bd0aa1cd9e550710a457` | `59d8aeee1addb77efffb323226eacc276fe9c475def82fc6db5ea6ddda7f9cc2` | target 0/3 pass; reference 3/3 pass |

The archive command for each row was:

```bash
git archive --format=tar --output=/tmp/ai-tools-<role>-<short-commit>.tar <full-commit>
```

The archives have no prefix. `git get-tar-commit-id` returned the recorded full
commit for all four archives. The tree was captured with
`git rev-parse <full-commit>^{tree}` and the archive digest with `sha256sum`.

## Evaluator-only defect inventory

This section and the adjacent graders must remain outside every model-visible
target mount.

### Target `23c1549`

Grader:
`tools/test_cross_package_defects_at_23c1549.py`, SHA-256
`6e2a8a48b3baf28ae0c5eb6c52784cba16c12d23c9ac37814666f23bc69524ab`.

1. `agent_lib` enforced `tool_not_granted` but omitted it from the shared
   blocked-policy classification.
2. packaged `llm_engines` data contained a private deployment address instead
   of a placeholder.
3. the publication-hygiene checker did not fail closed when Git could not
   provide a tracked-file inventory.

The fixes were already present by reference `49026ea`; they were made
independently of this repository-assessment harness.

### Target `7d37920`

Grader:
`tools/test_engram_boundary_defects_at_7d37920.py`, SHA-256
`6df8cf5c9ad7eb29f06e9e0db34dedd4801bdfaa66860028b53f98ddb484efe8`.

1. project and session identifiers could escape their intended storage roots.
2. persistent memory directories and JSONL files inherited permissive umask
   modes instead of enforcing private modes.
3. tenant policy was not enforced when deleting an episode belonging to a
   different tenant.

The fixes were already present by reference `8e2e9e5`; they were made
independently of this repository-assessment harness.

## Validation method and result

Each commit was exported with `git archive` into a fresh directory. Pytest ran
with plugin autoload disabled, bytecode writing disabled, live-repository
conftest discovery disabled, and source paths pointed only at the exported
tree. The load-bearing command shape was:

```bash
cd <exported-tree>
ASSESSMENT_REPO_ROOT=<exported-tree> \
PYTHONPATH=<exported-package-source-paths> \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
PYTHONDONTWRITEBYTECODE=1 \
/home/cybernaif/repos/ai_tools/.venv/bin/python -m pytest \
  -c /dev/null --noconftest -p no:cacheprovider -q <external-grader>
```

Observed outcomes:

| Grader | Target | Corrected reference |
| --- | --- | --- |
| cross-package `23c1549` grader | 3 failed | 3 passed |
| Engram `7d37920` grader | 3 failed | 3 passed |

An earlier Engram validation attempt is invalid and excluded. Although
conftest loading was disabled, pytest still read the live checkout's
`pytest.ini`, whose `pythonpath` setting injected current package sources and
made the old target appear to pass. Re-running with `-c /dev/null` produced the
required 3-fail/3-pass split. This is runner isolation evidence, not a model or
grader result.

## Candidate not selected

Target `f9451b2c7f47624003508b8e8a0e9ef1b9345bfd` also has a valid external
three-defect mail-triage grader: target 3 failed, corrected reference
`8d3624386696ecdeeba6263813134570fad7a571` 3 passed. It is not selected for a
matched staged/adaptive study because it predates the final nine-scope package
topology. The grader remains useful as an independently executable candidate,
not as evidence from a completed model experiment.

## Decision boundary

Before a confirmatory Phase 2 campaign, an evaluator other than the harness
author must select or independently approve target construction without using
the proposed prompts, then control the oracle until every report is final.
Absent that step, any run on these two targets must be labelled exploratory and
model-blind, not independently blinded confirmation.

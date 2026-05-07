# NEXT_STEP.md

Run this first:

    git status --short

Then do:

- Identify which modified files belong to the current stabilization checkpoint.
- Separate unrelated pre-existing WIP from the stabilization repairs if possible.
- Consider creating a named local checkpoint commit or archive before starting new architecture work.

Current green checks:
- `engram_lite/tests`
- `integration_tests/test_augmenter_spine.py`
- `scripts/check_teaching_artifacts.py`
- `engram/tests`
- `integration_tests`
- `language_tutor/tests`
- `llm_inspector/tests`

Do not start new feature work until the current passing state has been preserved.
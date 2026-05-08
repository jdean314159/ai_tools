"""
pytest conftest — makes all harness tests discoverable by pytest.

The harness uses its own runner (run_tests.py) but every test function
also works as a plain pytest test: they raise on failure, return None on
pass, and raise SkipTest (which pytest recognises) on skip.

Run with:
    PYTHONPATH=. pytest tests/harness/ -v
    PYTHONPATH=. pytest tests/harness/ -v -k "Working Memory"
    PYTHONPATH=. pytest tests/harness/ -v --tb=short
"""
# Raise the open-file-descriptor limit before any tests run.
# Kuzu opens multiple file handles per database; the default limit (1024)
# is easily exhausted when many tests with SemanticMemory/ProjectMemory run
# sequentially.
try:
    import resource as _resource
    _soft, _hard = _resource.getrlimit(_resource.RLIMIT_NOFILE)
    _target = min(max(_soft, 4096), _hard) if _hard > 0 else max(_soft, 4096)
    if _target > _soft:
        _resource.setrlimit(_resource.RLIMIT_NOFILE, (_target, _hard))
except Exception:
    pass

# Ensure ProjectMemory background daemons do not leak between tests.
# Some tests use pytest tmp_path directly rather than harness.TempDir.
try:
    import pytest
except Exception:  # pragma: no cover - pytest always imports conftest under pytest
    pytest = None

if pytest is not None:
    @pytest.fixture(autouse=True)
    def _close_project_memory_instances_after_test():
        yield
        try:
            from engram.project_memory import ProjectMemory
            ProjectMemory.close_all_live_instances()
        except Exception:
            pass

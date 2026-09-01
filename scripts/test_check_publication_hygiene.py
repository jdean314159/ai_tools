from __future__ import annotations

# hygiene: ignore-fixture-references

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).with_name("check_publication_hygiene.py")
SPEC = importlib.util.spec_from_file_location("check_publication_hygiene", SCRIPT_PATH)
assert SPEC is not None
checker = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


REQUIRED_DOCS = (
    "README.md",
    "ADR_INDEX.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "CONTRIBUTING.md",
)


def _write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _clean_root(tmp_path: Path) -> Path:
    for name in REQUIRED_DOCS:
        _write(tmp_path / name)
    return tmp_path


@pytest.fixture()
def hygiene_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _clean_root(tmp_path)
    monkeypatch.setattr(checker, "ROOT", root)
    monkeypatch.setattr(checker, "_git_tracked_files", lambda: set())
    return root


def _track(monkeypatch: pytest.MonkeyPatch, *paths: Path) -> None:
    monkeypatch.setattr(checker, "_git_tracked_files", lambda: {path.resolve() for path in paths})


def test_untracked_banned_dir_fails_strict_and_warns_tracked_only(
    hygiene_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(hygiene_root / ".pytest_cache" / "v" / "cache")

    assert checker.main([]) == 1
    strict_output = capsys.readouterr().out
    assert "Untracked banned artifacts:" in strict_output
    assert ".pytest_cache" in strict_output

    assert checker.main(["--tracked-only"]) == 0
    tracked_only_output = capsys.readouterr().out
    assert "Publication hygiene warnings:" in tracked_only_output
    assert "Untracked banned artifacts:" in tracked_only_output
    assert ".pytest_cache" in tracked_only_output


def test_tracked_banned_file_fails_in_both_modes(
    hygiene_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pyc = _write(hygiene_root / "pkg" / "module.pyc")
    _track(monkeypatch, pyc)

    assert checker.main([]) == 1
    strict_output = capsys.readouterr().out
    assert "Tracked banned artifacts:" in strict_output
    assert "pkg/module.pyc" in strict_output

    assert checker.main(["--tracked-only"]) == 1
    tracked_only_output = capsys.readouterr().out
    assert "Tracked banned artifacts:" in tracked_only_output
    assert "pkg/module.pyc" in tracked_only_output


def test_banned_dir_reported_once_not_per_child(hygiene_root: Path) -> None:
    _write(hygiene_root / "__pycache__" / "a.pyc")
    _write(hygiene_root / "__pycache__" / "b.pyc")
    _write(hygiene_root / "__pycache__" / "c.pyc")

    findings = checker._classify_findings()

    assert findings["untracked"] == {"__pycache__": [Path("__pycache__")]}


def test_egg_info_suffix_dir_is_caught(hygiene_root: Path) -> None:
    _write(hygiene_root / "pkg.egg-info" / "PKG-INFO")

    findings = checker._classify_findings()

    assert findings["untracked"] == {"*.egg-info": [Path("pkg.egg-info")]}


def test_ruff_cache_is_caught(hygiene_root: Path) -> None:
    _write(hygiene_root / ".ruff_cache" / "0.15.14" / "cache")

    findings = checker._classify_findings()

    assert findings["untracked"] == {".ruff_cache": [Path(".ruff_cache")]}


def test_language_tutor_example_is_caught_literal(hygiene_root: Path) -> None:
    _write(hygiene_root / ".language_tutor_example" / "memory" / "records.jsonl")

    findings = checker._classify_findings()

    assert findings["untracked"] == {".language_tutor_example": [Path(".language_tutor_example")]}


def test_clean_tree_passes_in_both_modes(
    hygiene_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert checker.main([]) == 0
    strict_output = capsys.readouterr().out
    assert "Mode: strict" in strict_output
    assert "Tracked banned artifacts: none" in strict_output
    assert "Untracked banned artifacts: none" in strict_output

    assert checker.main(["--tracked-only"]) == 0
    tracked_only_output = capsys.readouterr().out
    assert "Mode: tracked-only" in tracked_only_output
    assert "Tracked banned artifacts: none" in tracked_only_output


def test_missing_required_doc_still_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(checker, "_git_tracked_files", lambda: set())

    assert checker.main([]) == 1


def test_distribution_license_must_match_root(
    hygiene_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package = hygiene_root / "pkg"
    _write(
        package / "pyproject.toml",
        '[project]\nname = "pkg"\nversion = "0.1.0"\nlicense = "MIT"\n',
    )
    _write(package / "LICENSE", "different")

    assert checker.main([]) == 1
    output = capsys.readouterr().out
    assert "project.license must be 'Apache-2.0'" in output
    assert "project.license-files must be ['LICENSE']" in output
    assert "LICENSE bytes differ from root LICENSE" in output


def test_distribution_license_alignment_passes(hygiene_root: Path) -> None:
    package = hygiene_root / "pkg"
    _write(
        package / "pyproject.toml",
        '[project]\nname = "pkg"\nversion = "0.1.0"\n'
        'license = "Apache-2.0"\nlicense-files = ["LICENSE"]\n',
    )
    _write(package / "LICENSE", (hygiene_root / "LICENSE").read_text(encoding="utf-8"))

    assert checker.main([]) == 0


def test_tool_only_pyproject_is_not_treated_as_distribution(hygiene_root: Path) -> None:
    _write(hygiene_root / "pyproject.toml", '[tool.ruff]\ntarget-version = "py310"\n')

    assert checker.main([]) == 0


def test_missing_git_metadata_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(checker, "ROOT", _clean_root(tmp_path))
    monkeypatch.setattr(
        checker.subprocess,
        "run",
        lambda *args, **kwargs: checker.subprocess.CompletedProcess(
            args=["git", "ls-files"], returncode=128, stdout="", stderr="not a repository"
        ),
    )

    assert checker.main([]) == 1
    output = capsys.readouterr().out
    assert "Tracked-file inventory is unavailable:" in output
    assert "exit status 128" in output


def test_empty_git_inventory_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(checker, "ROOT", _clean_root(tmp_path))
    monkeypatch.setattr(
        checker.subprocess,
        "run",
        lambda *args, **kwargs: checker.subprocess.CompletedProcess(
            args=["git", "ls-files"], returncode=0, stdout="", stderr=""
        ),
    )

    assert checker.main([]) == 1
    output = capsys.readouterr().out
    assert "Tracked-file inventory is unavailable:" in output
    assert "empty tracked-file inventory" in output


def test_private_details_in_any_distribution_content_suffix_fail(
    hygiene_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package = hygiene_root / "pkg"
    _write(
        package / "pyproject.toml",
        '[project]\nname = "pkg"\nversion = "0.1.0"\n'
        'license = "Apache-2.0"\nlicense-files = ["LICENSE"]\n'
        '[tool.setuptools.packages.find]\nwhere = ["src"]\n',
    )
    _write(package / "LICENSE", (hygiene_root / "LICENSE").read_text(encoding="utf-8"))
    leaked = _write(package / "src" / "pkg" / "deployment.cfg", "host=192.168.50.225\n")
    _track(monkeypatch, leaked)

    assert checker.main([]) == 1
    output = capsys.readouterr().out
    assert "Distribution content must not contain private deployment details:" in output
    assert "pkg/src/pkg/deployment.cfg: 192.168.50.225" in output


def test_private_details_outside_distribution_content_are_not_rewritten(
    hygiene_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provenance = _write(
        hygiene_root / "docs" / "historical-record.md",
        "Observed endpoint 192.168.50.225 during the frozen run.\n",
    )
    _track(monkeypatch, provenance)

    assert checker.main([]) == 0


def test_skip_dirs_are_not_descended(hygiene_root: Path) -> None:
    _write(hygiene_root / ".venv" / "lib" / "ignored.pyc")

    findings = checker._classify_findings()

    assert findings == {"tracked": {}, "untracked": {}}


def test_banned_files_in_multiple_directories_are_all_found(hygiene_root: Path) -> None:
    _write(hygiene_root / "one" / "a.pyc")
    _write(hygiene_root / "two" / "b.pyo")
    _write(hygiene_root / "three" / "c.orig")

    findings = checker._classify_findings()
    found = sorted(path for paths in findings["untracked"].values() for path in paths)

    assert found == [
        Path("one/a.pyc"),
        Path("three/c.orig"),
        Path("two/b.pyo"),
    ]


def test_referenced_untracked_fixture_fails_in_both_modes(
    hygiene_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(
        hygiene_root / "pkg" / "tests" / "test_logs.py",
        "from pathlib import Path\n"
        "FIXTURES = Path(__file__).parent / 'fixtures'\n"
        "def test_log():\n"
        "    assert (FIXTURES / 'sample.log').read_text()\n",
    )
    _write(hygiene_root / "pkg" / "tests" / "fixtures" / "sample.log", "warning\n")

    assert checker.main([]) == 1
    strict_output = capsys.readouterr().out
    assert "Referenced fixture files must be tracked:" in strict_output
    assert "pkg/tests/test_logs.py references untracked fixture" in strict_output
    assert "pkg/tests/fixtures/sample.log" in strict_output

    assert checker.main(["--tracked-only"]) == 1
    tracked_only_output = capsys.readouterr().out
    assert "Referenced fixture files must be tracked:" in tracked_only_output


def test_referenced_tracked_fixture_passes(
    hygiene_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write(
        hygiene_root / "pkg" / "tests" / "test_logs.py",
        "from pathlib import Path\n"
        "FIXTURES = Path(__file__).parent / 'fixtures'\n"
        "def test_log():\n"
        "    assert (FIXTURES / 'sample.log').read_text()\n",
    )
    fixture = _write(hygiene_root / "pkg" / "tests" / "fixtures" / "sample.log", "warning\n")
    _track(monkeypatch, fixture)

    assert checker.main([]) == 0


def test_referenced_fixture_directory_passes_with_tracked_descendant(
    hygiene_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write(
        hygiene_root / "pkg" / "tests" / "test_corpus.py",
        "from pathlib import Path\nCORPUS = Path(__file__).parent / 'fixtures' / 'eval'\n",
    )
    fixture = _write(
        hygiene_root / "pkg" / "tests" / "fixtures" / "eval" / "case.json",
        "{}",
    )
    _track(monkeypatch, fixture)

    assert checker.main([]) == 0


def test_referenced_missing_fixture_fails(hygiene_root: Path) -> None:
    _write(
        hygiene_root / "pkg" / "tests" / "test_logs.py",
        "from pathlib import Path\n"
        "FIXTURES = Path(__file__).parent / 'fixtures'\n"
        "def test_log():\n"
        "    assert (FIXTURES / 'missing.log').read_text()\n",
    )

    assert checker.main([]) == 1


def test_direct_fixture_string_reference_must_be_tracked(
    hygiene_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write(
        hygiene_root / "pkg" / "tests" / "test_logs.py",
        "def test_log():\n    assert open('fixtures/direct.log').read()\n",
    )
    fixture = _write(hygiene_root / "pkg" / "tests" / "fixtures" / "direct.log", "warning\n")
    _track(monkeypatch, fixture)

    references = checker._fixture_references()

    assert references[0].fixture_path == fixture.resolve()
    assert checker.main([]) == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))

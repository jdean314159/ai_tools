from pathlib import Path

import pytest

from scripts.clean_review_bundle import REPO_ROOT, _validated_target, clean_review_bundle


def test_live_checkout_is_rejected():
    with pytest.raises(ValueError, match="this checkout"):
        _validated_target(str(Path(__file__).resolve().parents[1]))


def test_package_inside_live_checkout_is_rejected():
    with pytest.raises(ValueError, match="inside it"):
        _validated_target(str(REPO_ROOT / "engram"))


def test_explicit_review_checkout_is_cleaned(tmp_path):
    target = tmp_path / "ai_tools_review"
    target.mkdir()
    (target / "pyproject.toml").write_text("[tool]\n", encoding="utf-8")
    (target / ".git").mkdir()
    (target / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    (target / ".pytest_cache").mkdir()
    (target / "memory.db").write_text("data", encoding="utf-8")
    keep = target / "README.md"
    keep.write_text("keep", encoding="utf-8")

    clean_review_bundle(_validated_target(str(target)))

    assert not (target / ".git").exists()
    assert not (target / ".pytest_cache").exists()
    assert not (target / "memory.db").exists()
    assert keep.read_text(encoding="utf-8") == "keep"

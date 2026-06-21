from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from text_tools import join_labels, normalize_title, score_bucket


def test_normalize_title() -> None:
    assert normalize_title(" hello_world ") == "Hello World"
    assert normalize_title("") == "Untitled"


def test_join_labels() -> None:
    assert join_labels([" alpha ", "", "beta"], separator="|") == "alpha|beta"


def test_score_bucket_boundaries() -> None:
    assert score_bucket(-1) == "invalid"
    assert score_bucket(0) == "low"
    assert score_bucket(59) == "low"
    assert score_bucket(60) == "medium"
    assert score_bucket(89) == "medium"
    assert score_bucket(90) == "high"

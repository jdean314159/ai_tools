"""Tests for rag_lib.eval.ragas_runner."""

from __future__ import annotations

import pytest
from rag_lib.errors import EvalError
from rag_lib.eval.ragas_runner import run_eval


class TestEvalGuards:
    def test_judge_llm_required(self):
        """D9: judge_llm=None must raise EvalError with actionable message."""
        with pytest.raises(EvalError, match="judge_llm"):
            run_eval(None, [], judge_llm=None)

    def test_error_message_explains_why(self):
        """Error message should explain self-evaluation bias."""
        with pytest.raises(EvalError) as exc_info:
            run_eval(None, [], judge_llm=None)
        msg = str(exc_info.value)
        assert "self-consistency" in msg or "same model" in msg

    def test_not_implemented_with_judge(self):
        """When judge_llm is provided, should raise NotImplementedError (Phase 3)."""
        with pytest.raises(NotImplementedError):
            run_eval(None, [], judge_llm="claude-haiku")

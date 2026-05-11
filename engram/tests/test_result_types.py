"""Unit tests for engram.memory.result_types.

TokenBudget, SynthesisHookConfig, and ContextResult are pure data classes
with no network or disk I/O, so tests are fast and self-contained.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from engram.memory.result_types import ContextResult, SynthesisHookConfig, TokenBudget


# ---------------------------------------------------------------------------
# TokenBudget
# ---------------------------------------------------------------------------

def test_token_budget_default_total():
    b = TokenBudget()
    assert b.total == b.working + b.episodic + b.semantic + b.cold + b.procedural


def test_token_budget_custom_values():
    b = TokenBudget(working=500, episodic=400, semantic=200, cold=200, procedural=100)
    assert b.total == 1400


def test_token_budget_zero():
    b = TokenBudget(working=0, episodic=0, semantic=0, cold=0, procedural=0)
    assert b.total == 0


# ---------------------------------------------------------------------------
# SynthesisHookConfig
# ---------------------------------------------------------------------------

def test_synthesis_hook_defaults():
    cfg = SynthesisHookConfig()
    assert cfg.enabled is False
    assert cfg.episode_threshold == 20
    assert cfg.approval_callback is None


def test_synthesis_hook_custom():
    cb = lambda s: True
    cfg = SynthesisHookConfig(enabled=True, episode_threshold=5, approval_callback=cb)
    assert cfg.enabled is True
    assert cfg.episode_threshold == 5
    assert cfg.approval_callback is cb


# ---------------------------------------------------------------------------
# ContextResult — construction and token counting
# ---------------------------------------------------------------------------

def test_context_result_empty_default():
    ctx = ContextResult()
    assert ctx.total_tokens == 0
    assert ctx.working == []
    assert ctx.episodic == []
    assert ctx.semantic == []
    assert ctx.cold == []
    assert ctx.neural_meta is None


def test_context_result_total_tokens():
    ctx = ContextResult(
        working_tokens=100,
        episodic_tokens=80,
        semantic_tokens=40,
        cold_tokens=40,
        procedural_tokens=20,
    )
    assert ctx.total_tokens == 280


# ---------------------------------------------------------------------------
# ContextResult.to_dict()
# ---------------------------------------------------------------------------

def test_to_dict_has_required_keys():
    ctx = ContextResult()
    d = ctx.to_dict()
    for key in ("working", "episodic", "semantic", "cold", "procedural", "token_counts"):
        assert key in d, f"Missing key: {key}"


def test_to_dict_token_counts_correct():
    ctx = ContextResult(working_tokens=10, episodic_tokens=20, semantic_tokens=5)
    d = ctx.to_dict()
    assert d["token_counts"]["working"] == 10
    assert d["token_counts"]["episodic"] == 20
    assert d["token_counts"]["total"] == 35


def test_to_dict_neural_meta_included_when_set():
    ctx = ContextResult(neural_meta={"surprise": 0.9})
    d = ctx.to_dict()
    assert "neural" in d
    assert d["neural"]["surprise"] == 0.9


def test_to_dict_neural_meta_absent_when_none():
    ctx = ContextResult()
    assert "neural" not in ctx.to_dict()


def test_to_dict_working_messages_serialised():
    msg = SimpleNamespace(role="user", content="Hello there")
    ctx = ContextResult(working=[msg])
    d = ctx.to_dict()
    assert d["working"][0] == {"role": "user", "content": "Hello there"}


# ---------------------------------------------------------------------------
# ContextResult.to_prompt_sections()
# ---------------------------------------------------------------------------

def test_to_prompt_sections_keys_always_present():
    ctx = ContextResult()
    sections = ctx.to_prompt_sections()
    for key in ("working", "episodic", "semantic", "cold"):
        assert key in sections


def test_to_prompt_sections_empty_values_when_no_content():
    ctx = ContextResult()
    sections = ctx.to_prompt_sections()
    assert sections["working"] == ""
    assert sections["episodic"] == ""
    assert sections["semantic"] == ""
    assert sections["cold"] == ""


def test_to_prompt_sections_working_memory():
    msg = SimpleNamespace(role="user", content="What is RAG?")
    ctx = ContextResult(working=[msg])
    sections = ctx.to_prompt_sections()
    assert "user" in sections["working"]
    assert "What is RAG?" in sections["working"]


def test_to_prompt_sections_semantic_preference():
    fact = {"type": "preference", "category": "language", "value": "Python"}
    ctx = ContextResult(semantic=[fact])
    sections = ctx.to_prompt_sections()
    assert "Python" in sections["semantic"]
    assert "language" in sections["semantic"]


def test_to_prompt_sections_cold_storage():
    ctx = ContextResult(cold=[{"text": "An old note."}, {"text": "Another note."}])
    sections = ctx.to_prompt_sections()
    assert "An old note." in sections["cold"]
    assert "Another note." in sections["cold"]


def test_to_prompt_sections_episodic_filters_transient():
    ep_real = SimpleNamespace(text="I prefer Python for scripts.")
    ep_transient = SimpleNamespace(text="Transient note: do not store this.")
    ctx = ContextResult(episodic=[ep_real, ep_transient])
    sections = ctx.to_prompt_sections()
    assert "Python" in sections["episodic"]
    assert "Transient" not in sections["episodic"]


# ---------------------------------------------------------------------------
# ContextResult.to_formatted_prompt()
# ---------------------------------------------------------------------------

def test_to_formatted_prompt_user_message_present():
    ctx = ContextResult()
    result = ctx.to_formatted_prompt(user_message="Tell me about RAG.")
    assert "Tell me about RAG." in result


def test_to_formatted_prompt_system_prompt_present():
    ctx = ContextResult()
    result = ctx.to_formatted_prompt(user_message="q", system_prompt="You are an expert.")
    assert "You are an expert." in result


def test_to_formatted_prompt_memory_wrapped():
    fact = {"type": "fact", "content": "The sky is blue."}
    ctx = ContextResult(semantic=[fact])
    result = ctx.to_formatted_prompt(user_message="What colour is the sky?")
    assert "The sky is blue." in result

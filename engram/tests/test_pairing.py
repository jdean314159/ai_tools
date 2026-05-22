from __future__ import annotations
import tempfile
from engram import ProjectMemory


def make_memory(tmpdir, **kwargs):
    return ProjectMemory(
        base_dir=tmpdir,
        project_id="test_pairing",
        session_id="s1",
        auto_pair_assistant=True,
        **kwargs,
    )


def test_basic_pairing(tmp_path):
    mem = make_memory(tmp_path)
    mem.add_turn("user", "What is Python?", "s1")
    mem.add_turn("assistant", "Python is a programming language.", "s1")
    stats = mem.get_stats()
    assert stats["episodic"]["pairing"]["paired_exchanges"] == 1
    assert stats["episodic"]["pairing"]["orphan_assistants"] == 0
    results = mem.search_episodes("Python", n=5)
    paired = any("User:" in r.text and "Assistant:" in r.text for r in results)
    assert paired, "Paired exchange not found in search results"
    mem.close()


def test_orphan_skip(tmp_path):
    mem = make_memory(tmp_path, orphan_assistant_handling="skip")
    mem.add_turn("assistant", "Hello orphan.", "s1")
    stats = mem.get_stats()
    assert stats["episodic"]["pairing"]["orphan_assistants"] == 1
    results = mem.search_episodes("orphan", n=10)
    assert all("orphan" not in r.text.lower() for r in results)
    mem.close()


def test_orphan_store(tmp_path):
    mem = make_memory(tmp_path, orphan_assistant_handling="store")
    mem.add_turn("assistant", "Orphaned response.", "s1")
    results = mem.search_episodes("orphaned", n=10)
    assert any("orphaned" in r.text.lower() for r in results)
    mem.close()


def test_pairing_disabled(tmp_path):
    mem = ProjectMemory(
        base_dir=tmp_path, project_id="np", session_id="s1",
        auto_pair_assistant=False,
    )
    mem.add_turn("user", "Question?", "s1")
    mem.add_turn("assistant", "Answer.", "s1")
    stats = mem.get_stats()
    assert stats["episodic"]["pairing"]["paired_exchanges"] == 0
    mem.close()


def test_get_paired_exchanges(tmp_path):
    mem = make_memory(tmp_path)
    for user, asst in [
        ("What is AI?", "Artificial intelligence."),
        ("What is ML?", "Machine learning."),
    ]:
        mem.add_turn("user", user, "s1")
        mem.add_turn("assistant", asst, "s1")
    exchanges = mem.get_paired_exchanges("What is", n=5)
    assert len(exchanges) >= 1
    assert all("user" in e and "assistant" in e for e in exchanges)
    mem.close()


def test_cross_session_no_pair(tmp_path):
    mem = make_memory(tmp_path)
    mem.add_turn("user", "Question in s1", "s1")
    mem.add_turn("assistant", "Answer in s2", "s2")  # different session
    stats = mem.get_stats()
    assert stats["episodic"]["pairing"]["orphan_assistants"] == 1
    mem.close()

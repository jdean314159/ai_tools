import hashlib
from pathlib import Path

from examples.vector_memory_probe import cases, suite_digest

def test_vector_suite_has_four_roles_and_unique_ids():
    suite=cases(); assert len(suite)==5
    ids=[m.memory_id for c in suite for m in c.memories]
    assert len(ids)==len(set(ids))==20
    assert all({m.role for m in c.memories}=={"relevant","conflict","near","irrelevant"} for c in suite)
    assert suite_digest().startswith("sha256:")

def test_committed_vector_artifact_is_pinned_and_private():
    path=Path(__file__).resolve().parents[1]/"docs/projects/runs/2026-08-30-engram-vector-retrieval-v1.json"
    content=path.read_bytes()
    assert hashlib.sha256(content).hexdigest()=="974785cf4dacb1d0da87df92dac07da4dae8992e9423fda33fd32c031a56b85e"
    decoded=content.decode()
    assert not any(x in decoded for x in ("/home/","cybernaif","Frankfurt Germany","Which European"))

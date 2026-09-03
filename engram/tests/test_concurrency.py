from __future__ import annotations

import fcntl
import os
from pathlib import Path

import pytest

from engram.concurrency import WriterLock


def test_stale_pid_text_is_overwritten_without_replacing_inode(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    lock_path = project_dir / WriterLock.LOCK_FILE
    lock_path.write_text("999999999\n", encoding="utf-8")
    original_inode = lock_path.stat().st_ino

    lock = WriterLock(project_dir)
    assert lock.acquire(timeout=0.1)
    try:
        assert lock_path.stat().st_ino == original_inode
        assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())
    finally:
        lock.release()


def test_dead_pid_text_cannot_bypass_an_active_kernel_lock(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    lock_path = project_dir / WriterLock.LOCK_FILE
    owner_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(owner_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.write(owner_fd, b"999999999\n")
    original_inode = lock_path.stat().st_ino

    contender = WriterLock(project_dir)
    try:
        with pytest.raises(RuntimeError, match="Writer lock held"):
            contender.acquire(timeout=0.01)
        assert lock_path.stat().st_ino == original_inode
    finally:
        fcntl.flock(owner_fd, fcntl.LOCK_UN)
        os.close(owner_fd)

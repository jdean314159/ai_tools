from __future__ import annotations
import fcntl
import os
import time
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _read_lock_pid(lock_path: Path) -> Optional[int]:
    """Read PID from lock file. Returns None if missing, empty, or non-numeric."""
    try:
        content = lock_path.read_text().strip()
        if content:
            return int(content)
    except (ValueError, OSError):
        pass
    return None


class WriterLock:
    """Single-writer file lock using flock().

    The lock pathname is persistent. Stale PID text is informational only and
    is overwritten after the kernel lock becomes available; unlinking a locked
    pathname could let two writers lock different inodes.
    """

    LOCK_FILE = ".writer.lock"

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.lock_path = self.project_dir / self.LOCK_FILE
        self._fd: Optional[int] = None

    def acquire(self, timeout: float = 5.0) -> bool:
        """Acquire write lock.

        Args:
            timeout: Seconds to wait before giving up on a live-process lock.

        Returns:
            True if acquired.

        Raises:
            RuntimeError: If a live process holds the lock after timeout.
        """
        self.project_dir.mkdir(parents=True, exist_ok=True)

        self._fd = os.open(str(self.lock_path), os.O_CREAT | os.O_WRONLY, 0o600)
        os.fchmod(self._fd, 0o600)
        deadline = time.monotonic() + timeout

        while True:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Write our PID
                os.truncate(self._fd, 0)
                os.lseek(self._fd, 0, os.SEEK_SET)
                os.write(self._fd, f"{os.getpid()}\n".encode())
                logger.debug(f"Writer lock acquired: {self.lock_path}")
                return True

            except BlockingIOError:
                # The kernel lock is authoritative. PID contents can be stale,
                # incomplete, or replaced while another writer still owns the
                # flock, so they are used only to improve the timeout message.
                holder_pid = _read_lock_pid(self.lock_path)
                if time.monotonic() > deadline:
                    holder = holder_pid or "unknown"
                    os.close(self._fd)
                    self._fd = None
                    raise RuntimeError(
                        f"Writer lock held by PID {holder} for {self.lock_path}. "
                        "Only one ProjectMemory writer per project is allowed."
                    )

                time.sleep(0.1)

    def release(self):
        """Release write lock."""
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except Exception as e:
                logger.debug(f"Error releasing lock: {e}")
            finally:
                self._fd = None
            logger.debug(f"Writer lock released: {self.lock_path}")

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()

    def __del__(self):
        try:
            self.release()
        except Exception:
            pass

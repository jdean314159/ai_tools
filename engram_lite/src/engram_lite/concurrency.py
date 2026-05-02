from __future__ import annotations
import fcntl
import os
import time
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _pid_is_alive(pid: int) -> bool:
    """Check if a PID is alive using signal 0. Returns False if dead or permission denied."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it — treat as alive
        return True


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

    Handles stale locks: if the lock file contains a PID that is no longer
    alive, the lock is considered stale and is forcibly acquired.
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

        # Check for stale lock before opening
        self._clear_stale_lock()

        self._fd = os.open(str(self.lock_path), os.O_CREAT | os.O_WRONLY, 0o600)
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
                # Another process has the flock — check if it's alive
                holder_pid = _read_lock_pid(self.lock_path)

                if holder_pid is not None and not _pid_is_alive(holder_pid):
                    # Stale lock from dead process
                    logger.warning(
                        f"Stale writer lock from dead PID {holder_pid}. "
                        f"Clearing and retrying."
                    )
                    os.close(self._fd)
                    self._fd = None
                    self._force_clear_lock()
                    return self.acquire(timeout=timeout)

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

    def _clear_stale_lock(self):
        """Remove lock file if PID inside is dead or file is unreadable."""
        if not self.lock_path.exists():
            return
        pid = _read_lock_pid(self.lock_path)
        if pid is None:
            # Empty or unreadable — treat as stale
            logger.warning(f"Unreadable lock file at {self.lock_path}, clearing.")
            self._force_clear_lock()
        elif not _pid_is_alive(pid):
            logger.warning(
                f"Stale lock from dead PID {pid} at {self.lock_path}, clearing."
            )
            self._force_clear_lock()

    def _force_clear_lock(self):
        """Remove lock file unconditionally."""
        try:
            self.lock_path.unlink(missing_ok=True)
        except OSError as e:
            logger.debug(f"Could not remove lock file: {e}")

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

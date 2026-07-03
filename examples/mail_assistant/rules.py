"""Reviewed, validated, conflict-detecting personal-rule writes."""
from __future__ import annotations

from dataclasses import dataclass
import difflib
import hashlib
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time

from mail_lib.personal_rules import RuleAction, RuleLoadResult, load_personal_rules
from mail_lib.thunderbird import MailMessage
from mail_lib.triage import Priority


@dataclass(frozen=True)
class RuleProposal:
    token: str
    diff: str
    validation: RuleLoadResult
    base_revision: str
    candidate_sha256: str
    expires_at: float


@dataclass(frozen=True)
class _PendingProposal:
    public: RuleProposal
    candidate: bytes


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _quoted(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _append_rule(current: bytes, rule: dict[str, str]) -> bytes:
    """Append an app-owned rule while preserving all existing bytes."""
    separator = b"" if not current or current.endswith(b"\n\n") else b"\n"
    if current and not current.endswith(b"\n"):
        separator = b"\n\n"
    lines = ["[[rule]]"]
    for key in ("sender", "domain", "subject", "priority", "action", "note"):
        if key in rule:
            lines.append(f"{key} = {_quoted(rule[key])}")
    return current + separator + ("\n".join(lines) + "\n").encode("utf-8")


class RuleTransactionService:
    def __init__(self, rules_path: str | Path, *, ttl_seconds: float = 600.0) -> None:
        self.rules_path = Path(rules_path)
        self.ttl_seconds = ttl_seconds
        self._pending: dict[str, _PendingProposal] = {}
        self._lock = threading.Lock()

    def _read_current(self) -> bytes:
        if self.rules_path.is_symlink():
            raise ValueError("Rules path must not be a symlink")
        try:
            return self.rules_path.read_bytes()
        except FileNotFoundError:
            return b""

    def propose(
        self,
        message: MailMessage,
        *,
        field: str,
        priority: Priority,
        action: RuleAction,
    ) -> RuleProposal:
        if field == "sender":
            value = message.sender.strip().lower()
        elif field == "domain":
            sender = message.sender.strip().lower()
            if "@" not in sender:
                raise ValueError("Selected message has no sender domain")
            value = sender.rsplit("@", 1)[1]
        elif field == "subject":
            value = message.subject.strip().lower()
        else:
            raise ValueError("field must be sender, domain, or subject")
        if not value:
            raise ValueError(f"Selected message has no {field} value")

        current = self._read_current()
        if current:
            current_validation = self._validate_bytes(current)
            if not current_validation.ok:
                raise ValueError("Existing personal rules are invalid; refusing to rewrite them")
        candidate = _append_rule(
            current,
            {field: value, "priority": priority.value, "action": action.value},
        )
        validation = self._validate_bytes(candidate)
        if not validation.ok:
            raise ValueError("Generated candidate did not pass personal-rule validation")

        token = secrets.token_urlsafe(32)
        expires_at = time.time() + self.ttl_seconds
        public = RuleProposal(
            token=token,
            diff="".join(
                difflib.unified_diff(
                    current.decode("utf-8").splitlines(keepends=True),
                    candidate.decode("utf-8").splitlines(keepends=True),
                    fromfile="personal_rules.toml (current)",
                    tofile="personal_rules.toml (proposed)",
                )
            ),
            validation=validation,
            base_revision=_digest(current),
            candidate_sha256=_digest(candidate),
            expires_at=expires_at,
        )
        with self._lock:
            now = time.time()
            self._pending = {
                key: value
                for key, value in self._pending.items()
                if value.public.expires_at >= now
            }
            self._pending[token] = _PendingProposal(public, candidate)
        return public

    def commit(self, token: str) -> RuleLoadResult:
        with self._lock:
            pending = self._pending.pop(token, None)
        if pending is None:
            raise ValueError("Unknown or already-used proposal token")
        if pending.public.expires_at < time.time():
            raise ValueError("Proposal token has expired")
        if _digest(self._read_current()) != pending.public.base_revision:
            raise RuntimeError("Rules file changed after proposal; review a new diff")
        validation = self._validate_bytes(pending.candidate)
        if not validation.ok or _digest(pending.candidate) != pending.public.candidate_sha256:
            raise ValueError("Proposal validation failed")
        self._atomic_write(pending.candidate)
        result = load_personal_rules(self.rules_path)
        if not result.ok:  # defensive: exact candidate was already validated
            raise RuntimeError("Committed rules could not be reloaded")
        return result

    def _validate_bytes(self, content: bytes) -> RuleLoadResult:
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".mail-rules-validate-", dir=self.rules_path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
            return load_personal_rules(Path(name))
        finally:
            Path(name).unlink(missing_ok=True)

    def _atomic_write(self, content: bytes) -> None:
        if self.rules_path.is_symlink():
            raise ValueError("Rules path must not be a symlink")
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".personal-rules-", dir=self.rules_path.parent)
        temporary = Path(name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.rules_path)
            directory_fd = os.open(self.rules_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)

"""Reviewed, validated, conflict-detecting personal-rule writes."""
from __future__ import annotations

from dataclasses import dataclass
import difflib
import hashlib
import os
from pathlib import Path
import re
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


def _comment_suffix(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote == '"':
            escaped = True
        elif character in {"'", '"'}:
            quote = None if quote == character else character if quote is None else quote
        elif character == "#" and quote is None:
            return value[index:]
    return ""


def _replace_assignment(block: str, key: str, value: str) -> tuple[str, bool]:
    pattern = re.compile(rf"(?m)^([ \t]*{re.escape(key)}[ \t]*=[ \t]*)(.*?)(\r?)$")
    match = pattern.search(block)
    if match is None:
        return block, False
    suffix = _comment_suffix(match.group(2))
    replacement = f"{match.group(1)}{_quoted(value)}"
    if suffix:
        replacement += " " + suffix.lstrip()
    replacement += match.group(3)
    return block[:match.start()] + replacement + block[match.end():], True


def _update_rule(current: bytes, rule_index: int, *, priority: str, action: str) -> bytes:
    text = current.decode("utf-8")
    markers = list(re.finditer(r"(?m)^[ \t]*\[\[rule\]\][^\r\n]*(?:\r?\n|$)", text))
    if not 1 <= rule_index <= len(markers):
        raise ValueError("Existing rule index could not be located")
    start = markers[rule_index - 1].start()
    end = markers[rule_index].start() if rule_index < len(markers) else len(text)
    block = text[start:end]
    block, priority_found = _replace_assignment(block, "priority", priority)
    if not priority_found:
        raise ValueError("Existing rule has no priority assignment")
    block, action_found = _replace_assignment(block, "action", action)
    if not action_found:
        newline = "\r\n" if "\r\n" in block else "\n"
        if not block.endswith(("\n", "\r")):
            block += newline
        block += f"action = {_quoted(action)}{newline}"
    return (text[:start] + block + text[end:]).encode("utf-8")


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
        message: MailMessage | None,
        *,
        field: str,
        priority: Priority,
        action: RuleAction,
        match_value: str | None = None,
    ) -> RuleProposal:
        if match_value is not None:
            value = match_value.strip().lower()
        elif message is None:
            raise ValueError("A message or match value is required")
        elif field == "sender":
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
        if field not in {"sender", "domain", "subject"}:
            raise ValueError("field must be sender, domain, or subject")
        if field == "domain" and "@" in value:
            raise ValueError("domain must not contain '@'")
        if not value:
            raise ValueError(f"Selected message has no {field} value")

        current = self._read_current()
        current_validation: RuleLoadResult | None = None
        if current:
            current_validation = self._validate_bytes(current)
            if not current_validation.ok:
                raise ValueError("Existing personal rules are invalid; refusing to rewrite them")
        matching = [] if current_validation is None else [
            rule
            for rule in current_validation.rules
            if getattr(rule, field) == value
            and all(getattr(rule, other) is None for other in {"sender", "domain", "subject"} - {field})
        ]
        if matching:
            candidate = _update_rule(
                current,
                max(rule.index for rule in matching),
                priority=priority.value,
                action=action.value,
            )
        else:
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

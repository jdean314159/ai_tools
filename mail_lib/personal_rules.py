"""File-backed deterministic personal rules for MAIL-01."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Sequence

from .thunderbird import MailMessage
from .triage import Priority, TriageResult


_PREDICATE_KEYS = ("sender", "domain", "subject")
_RULE_KEYS = frozenset((*_PREDICATE_KEYS, "priority", "note"))
_PREDICATE_WEIGHTS = {"sender": 3, "domain": 2, "subject": 1}


@dataclass(frozen=True)
class PersonalRule:
    index: int
    sender: str | None
    domain: str | None
    subject: str | None
    priority: Priority
    note: str | None
    specificity: tuple[int, int]


@dataclass(frozen=True)
class RuleLoadResult:
    ok: bool
    rules: tuple[PersonalRule, ...] = ()
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def empty_rule_result() -> RuleLoadResult:
    """Return a valid empty ruleset for the normal absent-default case."""
    return RuleLoadResult(ok=True)


def load_personal_rules(path: Path) -> RuleLoadResult:
    """Load and strictly validate a TOML personal-rule file without raising."""
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return RuleLoadResult(ok=False, errors=(f"Could not load rules file {path}: {exc}",))

    errors: list[str] = []
    unknown_top_level = sorted(set(data) - {"rule"})
    if unknown_top_level:
        errors.append(f"Unknown top-level key(s): {', '.join(unknown_top_level)}")

    raw_rules = data.get("rule", [])
    if not isinstance(raw_rules, list) or any(not isinstance(item, dict) for item in raw_rules):
        errors.append("Top-level 'rule' must be an array of tables ([[rule]]).")
        return RuleLoadResult(ok=False, errors=tuple(errors))

    compiled: list[PersonalRule] = []
    for index, raw_rule in enumerate(raw_rules, start=1):
        rule_errors: list[str] = []
        unknown_rule_keys = sorted(set(raw_rule) - _RULE_KEYS)
        if unknown_rule_keys:
            rule_errors.append(f"unknown key(s): {', '.join(unknown_rule_keys)}")

        normalized: dict[str, str | None] = {}
        for key in _PREDICATE_KEYS:
            value = raw_rule.get(key)
            if value is None:
                normalized[key] = None
            elif not isinstance(value, str):
                normalized[key] = None
                rule_errors.append(f"{key} must be a string")
            elif not value.strip():
                normalized[key] = None
                rule_errors.append(f"{key} must not be empty")
            else:
                normalized[key] = value.strip().lower()

        sender = normalized["sender"]
        domain = normalized["domain"]
        subject = normalized["subject"]
        if domain and "@" in domain:
            rule_errors.append("domain must not contain '@'")
        if sender and domain:
            rule_errors.append("sender and domain must not appear in the same rule")
        if not any((sender, domain, subject)):
            rule_errors.append("at least one of sender, domain, or subject is required")

        raw_priority = raw_rule.get("priority")
        priority: Priority | None = None
        if not isinstance(raw_priority, str):
            rule_errors.append("priority is required and must be a string")
        else:
            try:
                priority = Priority(raw_priority)
            except ValueError:
                allowed = ", ".join(item.value for item in Priority)
                rule_errors.append(f"priority must be one of: {allowed}")

        raw_note = raw_rule.get("note")
        note: str | None
        if raw_note is None:
            note = None
        elif not isinstance(raw_note, str):
            note = None
            rule_errors.append("note must be a string")
        else:
            note = raw_note.strip() or None

        if rule_errors:
            errors.extend(f"Rule #{index}: {error}" for error in rule_errors)
            continue

        assert priority is not None
        predicate_names = tuple(
            key for key, value in (("sender", sender), ("domain", domain), ("subject", subject))
            if value is not None
        )
        specificity = (
            len(predicate_names),
            sum(_PREDICATE_WEIGHTS[key] for key in predicate_names),
        )
        compiled.append(
            PersonalRule(
                index=index,
                sender=sender,
                domain=domain,
                subject=subject,
                priority=priority,
                note=note,
                specificity=specificity,
            )
        )

    if errors:
        return RuleLoadResult(ok=False, errors=tuple(errors))

    warnings = _collision_warnings(compiled)
    return RuleLoadResult(ok=True, rules=tuple(compiled), warnings=warnings)


def _predicate_values(rule: PersonalRule) -> tuple[str | None, str | None, str | None]:
    return (rule.sender, rule.domain, rule.subject)


def _collision_warnings(rules: Sequence[PersonalRule]) -> tuple[str, ...]:
    warnings: list[str] = []
    for position, left in enumerate(rules):
        for right in rules[position + 1:]:
            if _predicate_values(left) == _predicate_values(right):
                warnings.append(
                    f"Rules #{left.index} and #{right.index} have identical predicates; "
                    f"rule #{left.index} wins by file order."
                )
                continue
            if (
                left.sender is None
                and left.domain is None
                and left.subject is not None
                and right.sender is None
                and right.domain is None
                and right.subject is not None
                and (left.subject in right.subject or right.subject in left.subject)
            ):
                warnings.append(
                    f"Rules #{left.index} and #{right.index} have nested subject substrings; "
                    "file order decides when both match."
                )
    return tuple(warnings)


def match_rule(rule: PersonalRule, message: MailMessage) -> bool:
    """Return whether every predicate in a personal rule matches a message."""
    sender = (message.sender or "").strip().lower()
    subject = (message.subject or "").lower()
    domain = sender.rsplit("@", 1)[1] if "@" in sender else None
    if rule.sender is not None and sender != rule.sender:
        return False
    if rule.domain is not None and domain != rule.domain:
        return False
    if rule.subject is not None and rule.subject not in subject:
        return False
    return True


def apply_to_message(
    result: TriageResult,
    message: MailMessage,
    rules: Sequence[PersonalRule],
) -> TriageResult:
    """Apply the most-specific matching personal rule to one message result."""
    if result.header_message_id != message.header_message_id:
        raise ValueError("message and triage result header_message_id values do not match")
    matches = [rule for rule in rules if match_rule(rule, message)]
    if not matches:
        return result
    selected = max(matches, key=lambda rule: rule.specificity)
    return TriageResult(
        header_message_id=result.header_message_id,
        priority=selected.priority,
        reason=selected.note or f"Matched personal rule #{selected.index}.",
        matched_rules=(*result.matched_rules, f"personal:{selected.index}"),
    )


def format_validation_report(result: RuleLoadResult) -> str:
    """Render deterministic human-readable rule validation output."""
    lines = ["Personal rules validation"]
    if result.ok:
        lines.append(f"Status: valid ({len(result.rules)} rule(s))")
        for rule in result.rules:
            predicates = ", ".join(
                f"{key}={value!r}"
                for key, value in (
                    ("sender", rule.sender),
                    ("domain", rule.domain),
                    ("subject", rule.subject),
                )
                if value is not None
            )
            lines.append(
                f"Rule #{rule.index}: {predicates}; priority={rule.priority.value}; "
                f"specificity={rule.specificity}"
            )
    else:
        lines.append("Status: invalid")
    lines.extend(f"Warning: {warning}" for warning in result.warnings)
    lines.extend(f"Error: {error}" for error in result.errors)
    return "\n".join(lines) + "\n"

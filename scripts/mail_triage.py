#!/usr/bin/env python3
"""Run MAIL-01 fixture-first local mail triage."""

# ruff: noqa: E402 -- direct script execution bootstraps the repository import path.
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mail_lib.digest import render_digest
from mail_lib.indexer import DEFAULT_INDEX_PATH, MailIndex
from mail_lib.personal_rules import (
    RuleLoadResult,
    apply_to_message,
    empty_rule_result,
    format_validation_report,
    load_personal_rules,
)
from mail_lib.thunderbird import iter_messages
from mail_lib.triage import triage_message, triage_messages


def _default_rules_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    root = Path(config_home) if config_home else Path.home() / ".config"
    return root / "mail_lib" / "personal_rules.toml"


def _rules_error(result: RuleLoadResult) -> str:
    details = "; ".join(result.errors) or "unknown validation error"
    return f"Personal rules disabled: {details}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic MAIL-01 triage.")
    parser.add_argument(
        "--profile", type=Path, help="Thunderbird profile or synthetic fixture root"
    )
    parser.add_argument(
        "--index", type=Path, default=None, help="Optional mail_lib index database path"
    )
    parser.add_argument(
        "--no-index", action="store_true", help="Do not persist processed-message state"
    )
    parser.add_argument("--rules", type=Path, help="Personal-rule TOML path")
    parser.add_argument(
        "--validate-rules",
        action="store_true",
        help="Validate personal rules without reading mail or the index",
    )
    args = parser.parse_args(argv)

    explicit_rules_path = args.rules is not None
    rules_path = args.rules if explicit_rules_path else _default_rules_path()
    if not rules_path.exists():
        if explicit_rules_path:
            print(f"Personal rules file does not exist: {rules_path}", file=sys.stderr)
            return 2
        rule_result = empty_rule_result()
    else:
        rule_result = load_personal_rules(rules_path)

    if args.validate_rules:
        print(format_validation_report(rule_result), end="")
        return 0 if rule_result.ok else 2

    if args.profile is None:
        parser.error("--profile is required unless --validate-rules is used")

    messages = list(iter_messages(args.profile))
    if not rule_result.ok:
        results = triage_messages(messages)
        print(render_digest(messages, results), end="")
        print(_rules_error(rule_result), file=sys.stderr)
        return 2

    results = [
        apply_to_message(triage_message(message), message, rule_result.rules)
        for message in messages
    ]
    if not args.no_index:
        index_path = args.index or DEFAULT_INDEX_PATH
        with MailIndex(index_path) as index:
            index.record_results(messages, results)
    print(render_digest(messages, results), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

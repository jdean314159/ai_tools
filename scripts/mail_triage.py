#!/usr/bin/env python3
"""Run MAIL-00 fixture-first local mail triage."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mail_lib.digest import render_digest
from mail_lib.indexer import MailIndex
from mail_lib.thunderbird import iter_messages
from mail_lib.triage import triage_messages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic MAIL-00 triage.")
    parser.add_argument("--profile", type=Path, required=True, help="Thunderbird profile or synthetic fixture root")
    parser.add_argument("--index", type=Path, default=None, help="Optional mail_lib index database path")
    parser.add_argument("--no-index", action="store_true", help="Do not persist processed-message state")
    args = parser.parse_args(argv)

    messages = list(iter_messages(args.profile))
    results = triage_messages(messages)
    if not args.no_index:
        index_path = args.index or (Path.home() / ".local" / "share" / "mail_lib" / "index.db")
        with MailIndex(index_path) as index:
            index.record_results(messages, results)
    print(render_digest(messages, results), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

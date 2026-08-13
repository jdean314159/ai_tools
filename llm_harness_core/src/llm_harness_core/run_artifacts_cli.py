"""Validate and summarize a durable run artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .run_artifacts import ArtifactValidationError, load_artifact, summarize_artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args(argv)
    try:
        artifact = load_artifact(args.artifact)
    except (OSError, json.JSONDecodeError, ArtifactValidationError) as exc:
        parser.exit(1, f"invalid run artifact: {exc}\n")
    print(json.dumps(summarize_artifact(artifact), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

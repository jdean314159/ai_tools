from __future__ import annotations

import argparse
from pathlib import Path

from llm_harness_core import SyntheticDataConfig, generate_synthetic_bundle, write_synthetic_bundle


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate synthetic memory and retrieval corpora for ai_tools labs."
    )
    parser.add_argument(
        "--topic", required=True, help="Topic label to use in generated records/documents."
    )
    parser.add_argument("--preset", choices=["clean", "noisy", "adversarial"], default="clean")
    parser.add_argument("--memory-count", type=int, default=24)
    parser.add_argument("--retrieval-count", type=int, default=24)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--output-dir",
        default="artifacts/synthetic_data",
        help="Directory to write JSONL/manifest files.",
    )
    args = parser.parse_args()

    bundle = generate_synthetic_bundle(
        SyntheticDataConfig(
            topic=args.topic,
            preset=args.preset,
            memory_count=args.memory_count,
            retrieval_count=args.retrieval_count,
            seed=args.seed,
        )
    )
    paths = write_synthetic_bundle(bundle, Path(args.output_dir))
    print("Synthetic data generated")
    print(f"Topic: {bundle.topic}")
    print(f"Preset: {bundle.preset}")
    print(f"Memory records: {len(bundle.memory_records)}")
    print(f"Retrieved documents: {len(bundle.retrieved_documents)}")
    for key, path in paths.items():
        print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

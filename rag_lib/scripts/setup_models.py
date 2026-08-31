#!/usr/bin/env python3
"""
scripts/setup_models.py

Pre-download all optional models needed by rag_lib.
Run once before first use, especially on air-gapped machines.

Usage:
    python scripts/setup_models.py              # NLTK only
    python scripts/setup_models.py --reranker   # + CrossEncoder model
"""

import argparse


def setup_nltk():
    print("Downloading NLTK punkt tokenizer...")
    try:
        import nltk

        nltk.download("punkt_tab", quiet=False)
        nltk.download("punkt", quiet=False)
        print("  NLTK punkt OK")
    except ImportError:
        print("  NLTK not installed (pip install nltk)")
    except Exception as exc:
        print(f"  NLTK download failed: {exc}")


def setup_reranker(model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
    print(f"Downloading CrossEncoder model: {model}")
    print("  Note: requires pip install rag-lib[rerank]")
    try:
        from sentence_transformers import CrossEncoder

        CrossEncoder(model)
        print("  CrossEncoder OK — cached at ~/.cache/huggingface/hub/")
    except ImportError:
        print("  sentence-transformers not installed: pip install rag-lib[rerank]")
    except Exception as exc:
        print(f"  CrossEncoder download failed: {exc}")
        print("  For air-gapped machines, manually copy the model to:")
        print(f"  ~/.cache/huggingface/hub/models--{model.replace('/', '--')}/")


def main():
    parser = argparse.ArgumentParser(description="Pre-download rag_lib models")
    parser.add_argument(
        "--reranker", action="store_true", help="Also download the CrossEncoder reranker model"
    )
    parser.add_argument(
        "--reranker-model",
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        help="CrossEncoder model name",
    )
    args = parser.parse_args()

    setup_nltk()
    if args.reranker:
        setup_reranker(args.reranker_model)

    print("\nSetup complete.")
    print("Next: ollama pull nomic-embed-text-v2-moe")


if __name__ == "__main__":
    main()

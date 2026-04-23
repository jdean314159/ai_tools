from __future__ import annotations

from pprint import pprint

from rag_lib.eval.broken_rag_lab import evaluate_repair, render_comparison


if __name__ == "__main__":
    query = "What region does Project Mercury deploy the nightly evaluation job to?"
    print(render_comparison(query))
    print("Evaluation summary:")
    pprint(evaluate_repair(query))

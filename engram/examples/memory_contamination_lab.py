from __future__ import annotations

from pprint import pprint

from engram.eval.memory_contamination_lab import DEFAULT_SCENARIOS, compare_scenario, evaluate_repair


if __name__ == "__main__":
    for scenario in DEFAULT_SCENARIOS:
        print(f"\n=== Scenario: {scenario.name} ===")
        print(compare_scenario(scenario.name))
    print("\n=== Evaluation summary ===")
    pprint(evaluate_repair())

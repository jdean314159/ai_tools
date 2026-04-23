from __future__ import annotations

from pprint import pprint

from agent_lib.eval import DEFAULT_SCENARIOS, evaluate_lab, render_scenario


if __name__ == '__main__':
    for scenario in DEFAULT_SCENARIOS:
        print(f"\n=== Scenario: {scenario.name} ===")
        print(render_scenario(scenario.name))
    print("\n=== Evaluation summary ===")
    pprint(evaluate_lab())

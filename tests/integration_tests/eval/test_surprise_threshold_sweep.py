from integration_tests.eval.surprise_threshold_sweep import (
    calibration_thresholds,
    evaluate_candidate,
    percentile,
)


def test_percentile_interpolates_calibration_values():
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5


def test_calibration_thresholds_include_current_and_deduplicate():
    assert calibration_thresholds([1.0, 2.0, 3.0], [0, 50, 100], 0.001) == [
        0.001,
        1.0,
        2.0,
        3.0,
    ]


def test_candidate_reports_write_ratio_and_quality_deltas():
    baseline = {
        "overall": {
            "recall_direct": 0.9,
            "recall_paraphrase": 0.9,
            "recall_decoy": 0.8,
        },
        "per_trial": [{"label": "contradict", "contradiction_bleed_rate": 0.4}],
    }
    neural = {
        "overall": {
            "recall_direct": 0.9,
            "recall_paraphrase": 0.9,
            "recall_decoy": 0.9,
            "judge_failures": 0,
            "injection_failures": 0,
        },
        "per_trial": [
            {
                "label": "contradict",
                "contradiction_bleed_rate": 0.3,
                "n_neural_observations": 4,
                "n_neural_writes": 2,
            }
        ],
    }

    row = evaluate_candidate(baseline, neural, 2.5)

    assert row["neural_write_ratio"] == 0.5
    assert row["passed"] is True

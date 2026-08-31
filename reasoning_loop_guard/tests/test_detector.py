from __future__ import annotations

from dataclasses import dataclass

import pytest

from reasoning_loop_guard import Intervention, detect_and_redirect


LOOP = (
    "Inspect the same files, compare the same symbols, and reconsider the same "
    "conclusion even though the evidence already establishes the answer. "
)


def test_returns_intervention_and_preserves_prefix_before_loop() -> None:
    prefix = " ".join(f"verified_unique_fact_{index}" for index in range(72)) + ". "
    text = prefix + LOOP * 12

    result = detect_and_redirect(text)

    assert isinstance(result, Intervention)
    assert result.confirmation_windows == 3
    assert result.repetition_fraction >= 0.35
    assert result.truncation_point >= len(prefix)
    assert result.truncation_point <= len(prefix) + len(LOOP) + 1
    assert result.truncation_point < len(text)
    assert text[: result.truncation_point].startswith(prefix)
    assert "finalize" in result.instruction.lower()


def test_accepts_chunked_typed_events_without_inserting_separators() -> None:
    @dataclass
    class Event:
        text: str

    prefix = " ".join(f"typed_event_fact_{index}" for index in range(72)) + ". "
    stream = [Event(prefix), {"text": LOOP * 7}, Event(LOOP * 7)]

    result = detect_and_redirect(stream)

    assert result is not None
    combined = "".join(
        event.text if isinstance(event, Event) else event["text"] for event in stream
    )
    assert combined[: result.truncation_point].startswith(prefix)


def test_a_single_repetition_spike_does_not_fire() -> None:
    repeated = LOOP * 2
    unique = " ".join(f"unique_{index}" for index in range(160))

    assert detect_and_redirect(repeated + unique) is None


def test_legitimate_enumeration_does_not_fire() -> None:
    steps = " ".join(
        f"Step {index}: inspect component_{index}, record result_{index}, then continue."
        for index in range(80)
    )

    assert detect_and_redirect(steps) is None


@pytest.mark.parametrize("stream", ["", "one short thought", [], ["brief"]])
def test_short_streams_do_not_fire(stream: object) -> None:
    assert detect_and_redirect(stream) is None  # type: ignore[arg-type]


def test_rejects_events_without_text() -> None:
    with pytest.raises(TypeError, match="event 0"):
        detect_and_redirect([{"content": "not a normalized reasoning block"}])

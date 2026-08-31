"""Detect sustained repetition in normalized reasoning text.

The detector intentionally has no knowledge of engines, transports, or agent
runtimes. Character offsets always refer to the exact concatenation of input
event text, so a caller can preserve the prefix without re-tokenizing it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from typing import Protocol, TypeAlias, runtime_checkable


_NGRAM_ORDER = 4
_WINDOW_TOKENS = 96
_WINDOW_STRIDE = 24
_REPETITION_THRESHOLD = 0.35
_CONFIRMATION_WINDOWS = 3
_FINALIZE_INSTRUCTION = (
    "Sufficient reasoning has occurred. Stop navigating and finalize the answer now "
    "using the evidence already gathered."
)
_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


@runtime_checkable
class _TextEvent(Protocol):
    text: str


ReasoningStream: TypeAlias = str | Iterable[str | Mapping[str, object] | _TextEvent]


@dataclass(frozen=True, slots=True)
class Intervention:
    """Advice returned when a reasoning loop has been confirmed.

    ``truncation_point`` is a character offset into the concatenated reasoning
    stream. Text before it is retained; text from it onward is the looping
    segment the caller may discard before resubmission.
    """

    truncation_point: int
    instruction: str
    loop_start_token: int
    repetition_fraction: float
    confirmation_windows: int


@dataclass(frozen=True, slots=True)
class _Token:
    normalized: str
    char_start: int


@dataclass(frozen=True, slots=True)
class _Window:
    start: int
    end: int
    repetition_fraction: float
    repeated_positions: tuple[int, ...]


def detect_and_redirect(reasoning_stream: ReasoningStream) -> Intervention | None:
    """Return redirect advice for a confirmed loop, otherwise ``None``.

    Detection is intentionally batch-pure: the complete iterable is consumed,
    no state is retained between calls, and no input event is modified.
    """

    text = _join_text(reasoning_stream)
    tokens = [
        _Token(match.group(0).casefold(), match.start()) for match in _TOKEN_RE.finditer(text)
    ]
    minimum = _WINDOW_TOKENS + (_CONFIRMATION_WINDOWS - 1) * _WINDOW_STRIDE
    if len(tokens) < minimum:
        return None

    windows = _windows(tokens)
    run: list[_Window] = []
    for window in windows:
        if window.repetition_fraction >= _REPETITION_THRESHOLD:
            run.append(window)
            if len(run) == _CONFIRMATION_WINDOWS:
                first = run[0]
                boundary = _loop_boundary(tokens, first)
                return Intervention(
                    truncation_point=tokens[boundary].char_start,
                    instruction=_FINALIZE_INSTRUCTION,
                    loop_start_token=boundary,
                    repetition_fraction=min(item.repetition_fraction for item in run),
                    confirmation_windows=len(run),
                )
        else:
            run.clear()
    return None


def _join_text(stream: ReasoningStream) -> str:
    if isinstance(stream, str):
        return stream

    parts: list[str] = []
    for index, event in enumerate(stream):
        if isinstance(event, str):
            parts.append(event)
            continue
        if isinstance(event, Mapping):
            value = event.get("text")
        else:
            value = getattr(event, "text", None)
        if not isinstance(value, str):
            raise TypeError(f"reasoning event {index} must be a string or expose string text")
        parts.append(value)
    return "".join(parts)


def _windows(tokens: list[_Token]) -> Iterable[_Window]:
    final_end = len(tokens)
    ends = list(range(_WINDOW_TOKENS, final_end + 1, _WINDOW_STRIDE))
    if ends[-1] != final_end:
        ends.append(final_end)
    for end in ends:
        start = end - _WINDOW_TOKENS
        ngrams: dict[tuple[str, ...], int] = {}
        repeated: list[int] = []
        last_start = end - _NGRAM_ORDER
        for position in range(start, last_start + 1):
            ngram = tuple(token.normalized for token in tokens[position : position + _NGRAM_ORDER])
            if ngram in ngrams:
                repeated.append(position)
            else:
                ngrams[ngram] = position
        total = max(1, last_start - start + 1)
        yield _Window(start, end, len(repeated) / total, tuple(repeated))


def _loop_boundary(tokens: list[_Token], window: _Window) -> int:
    """Find the first repeat backed by an earlier n-gram in the detection window."""

    if not window.repeated_positions:
        return window.start

    # Ignore isolated repeated phrases near the front. The selected boundary
    # must begin a suffix whose repetition density independently clears the
    # detector threshold; this keeps boilerplate in enumerations from becoming
    # a premature truncation point.
    repeated = set(window.repeated_positions)
    total_positions = window.end - _NGRAM_ORDER + 1
    boundary = window.repeated_positions[0]
    for candidate in window.repeated_positions:
        suffix_positions = total_positions - candidate
        if suffix_positions <= 0:
            continue
        suffix_repeats = sum(position >= candidate for position in repeated)
        if suffix_repeats / suffix_positions >= _REPETITION_THRESHOLD:
            boundary = candidate
            break

    # For exact cycles, recover the actual onset rather than merely the first
    # repeat visible in the detection window. N-grams inside one cycle agree on
    # its period, making the modal occurrence distance a stable estimate.
    positions_by_ngram: dict[tuple[str, ...], list[int]] = {}
    for position in range(window.start, window.end - _NGRAM_ORDER + 1):
        ngram = tuple(token.normalized for token in tokens[position : position + _NGRAM_ORDER])
        positions_by_ngram.setdefault(ngram, []).append(position)
    distances = Counter(
        current - previous
        for positions in positions_by_ngram.values()
        for previous, current in zip(positions, positions[1:])
        if current > previous
    )
    if not distances:
        return boundary

    period, support = distances.most_common(1)[0]
    if support < _NGRAM_ORDER or period < _NGRAM_ORDER:
        return boundary

    normalized = [token.normalized for token in tokens]
    while boundary >= 2 * period:
        previous = normalized[boundary - period : boundary]
        prior = normalized[boundary - 2 * period : boundary - period]
        if prior != previous:
            break
        boundary -= period
    return boundary

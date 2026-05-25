"""
Spanish content for the tutor slice.

Domain logic harvested from ``language_tutor/content/spanish.py`` — a small
representative subset, kept deliberately tiny for an acceptance-test slice.
This module has no dependency on engram or llm_engines; it is pure content.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VocabItem:
    spanish: str
    english: str
    example: str


# A small harvested set. The real tutor imports Duolingo exports and a much
# larger conjugation table; this subset is enough to exercise the turn loop.
STARTER_VOCAB: list[VocabItem] = [
    VocabItem("ser", "to be (permanent)", "Yo soy estudiante."),
    VocabItem("estar", "to be (state/location)", "Estoy en casa."),
    VocabItem("tener", "to have", "Tengo dos hermanos."),
    VocabItem("hacer", "to do/make", "Hago la tarea."),
    VocabItem("querer", "to want/love", "Quiero aprender español."),
]


SYSTEM_PROMPT = (
    "You are a patient Spanish tutor for an English-speaking learner. "
    "Reply in simple Spanish, then give a one-line English gloss. "
    "Gently correct mistakes. Keep replies short."
)


def vocab_seed_text() -> str:
    """Render the starter vocab as memory-seedable lines."""
    return "\n".join(
        f"{v.spanish} = {v.english} (e.g. {v.example})" for v in STARTER_VOCAB
    )

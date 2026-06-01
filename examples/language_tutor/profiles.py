from __future__ import annotations

from dataclasses import dataclass
from random import choice


@dataclass(frozen=True)
class LanguageProfile:
    code: str
    name: str
    native_name: str
    system_prompt: str
    greeting: str
    starters: tuple[str, ...]
    whisper_language: str

    def starter(self) -> str:
        return choice(self.starters) if self.starters else self.greeting


SPANISH = LanguageProfile(
    code="es",
    name="Spanish",
    native_name="Espanol",
    system_prompt=(
        "You are a professional Spanish tutor. Reply in clear natural Spanish, "
        "correct mistakes gently, introduce useful vocabulary in context, and "
        "use English only for concise grammar explanations when needed."
    ),
    greeting="Hola. Practiquemos espanol juntos.",
    starters=(
        "Como estas hoy?",
        "Que hiciste ayer?",
        "Cual es tu comida favorita?",
        "Que te gusta hacer en tu tiempo libre?",
    ),
    whisper_language="es",
)


LATIN = LanguageProfile(
    code="la",
    name="Latin",
    native_name="Latina",
    system_prompt=(
        "You are a Classical Latin tutor. Help with vocabulary, grammar, "
        "reading comprehension, and pronunciation. Use simple Latin when useful "
        "and English for grammar explanations."
    ),
    greeting="Salve. Latine exerceamus.",
    starters=(
        "Quid agis hodie?",
        "Quid heri fecisti?",
        "Cur Latine discere vis?",
        "Quid legis nunc?",
    ),
    whisper_language="la",
)


def get_profile(language: str) -> LanguageProfile:
    normalized = language.strip().lower()
    if normalized in {"spanish", "es", "espanol", "espanol"}:
        return SPANISH
    if normalized in {"latin", "la", "latina"}:
        return LATIN
    raise ValueError(f"Unsupported language: {language}")


SPANISH_CONTENT = {
    "vocabulary": {
        "aprender": "to learn",
        "comida": "food",
        "viajar": "to travel",
        "libro": "book",
    },
    "sentences": (
        ("Estoy aprendiendo espanol.", "I am learning Spanish."),
        ("Me gusta leer libros.", "I like to read books."),
        ("Ayer visite a mi familia.", "Yesterday I visited my family."),
    ),
    "verbs": {
        "ser": {"yo": "soy", "tu": "eres", "el": "es"},
        "ir": {"yo": "voy", "tu": "vas", "el": "va"},
        "tener": {"yo": "tengo", "tu": "tienes", "el": "tiene"},
    },
    "prepositions": (("pensar", "en", "to think about"), ("sonar", "con", "to dream about")),
}


LATIN_CONTENT = {
    "vocabulary": {
        "puella": "girl",
        "aqua": "water",
        "porto": "I carry",
        "liber": "book",
    },
    "sentences": (
        ("Puella aquam portat.", "The girl carries water."),
        ("Marcus librum legit.", "Marcus reads a book."),
        ("Roma in Italia est.", "Rome is in Italy."),
    ),
    "verbs": {
        "sum": {"1s": "sum", "2s": "es", "3s": "est"},
        "porto": {"1s": "porto", "2s": "portas", "3s": "portat"},
    },
    "prepositions": (("in", "ablative", "in/on"), ("ad", "accusative", "to/toward")),
}


def get_content(language: str) -> dict:
    profile = get_profile(language)
    return LATIN_CONTENT if profile.code == "la" else SPANISH_CONTENT

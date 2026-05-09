"""
Project-Specific Helper Functions for Semantic Memory

Convenience methods that sit on top of the SQLite semantic layer.
All storage uses the three core tables: facts, preferences, events.
FTS5 full-text search is used for approximate matching.

Graph-traversal queries (shortest paths, multi-hop relationships) that
require a graph database are not implementable on the flat SQLite schema
and are marked explicitly.  They return [] and log a WARNING so callers
know they need the Kuzu graph backend when those features are required.

Author: Jeffrey Dean
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from .semantic_memory import SemanticMemory

logger = logging.getLogger(__name__)

_VOCAB_PREFIX = "vocab"
_MASTERY_CATEGORY = "mastery"
_SNIPPET_PREFIX = "snippet"
_COMMAND_PREFIX = "command"
_PHOTO_PREFIX = "photo"


def _graph_not_available(method: str) -> list:
    logger.warning(
        "%s requires graph traversal (Kuzu backend). "
        "SQLite backend returns []. Re-enable graph store to use this method.",
        method,
    )
    return []


# ---------------------------------------------------------------------------
# Programming Assistant
# ---------------------------------------------------------------------------

class ProgrammingAssistantHelpers:
    """Semantic helpers for the programming assistant project type."""

    def __init__(self, memory: SemanticMemory) -> None:
        self.memory = memory

    def find_similar_bugs(self, error_message: str, limit: int = 5) -> list:
        """Find facts containing similar error terms via FTS5 search."""
        results = self.memory.search_generic_memories(error_message, limit=limit * 2)
        bug_rows = [r for r in results if r.get("source") in ("bug", "error", "exception")]
        if not bug_rows:
            bug_rows = [r for r in results if r.get("type") == "fact"]
        return bug_rows[:limit]

    def store_bug(
        self,
        error_type: str,
        message: str,
        solution: str,
        *,
        confidence: float = 0.8,
    ) -> None:
        """Store a bug/solution pair as a fact for later FTS retrieval."""
        content = f"Bug: {error_type}: {message} | Solution: {solution}"
        self.memory.add_fact(
            content,
            confidence=confidence,
            source="bug",
            metadata={"error_type": error_type, "message": message, "solution": solution},
        )

    def store_snippet(
        self,
        snippet_id: str,
        code: str,
        description: str,
        *,
        language: str = "python",
        confidence: float = 0.8,
    ) -> None:
        """Store a code snippet as a fact."""
        content = f"Snippet {snippet_id} ({language}): {description}"
        self.memory.add_fact(
            content,
            confidence=confidence,
            source=_SNIPPET_PREFIX,
            fact_id=f"{_SNIPPET_PREFIX}_{snippet_id}",
            metadata={"snippet_id": snippet_id, "language": language, "code": code},
        )

    def add_code_dependency(self, from_snippet_id: str, to_snippet_id: str, **_: Any) -> list:
        return _graph_not_available("add_code_dependency")

    def find_learning_path(self, target_concept: str) -> list:
        return _graph_not_available("find_learning_path")

    def find_prerequisites(self, concept_name: str, max_depth: int = 3) -> list:
        return _graph_not_available("find_prerequisites")

    def find_alternatives(self, snippet_id: str) -> list:
        return _graph_not_available("find_alternatives")


# ---------------------------------------------------------------------------
# Language Tutor
# ---------------------------------------------------------------------------

class LanguageTutorHelpers:
    """Semantic helpers for the language tutor project type.

    Storage layout:
    - Vocabulary words: facts table, source=_VOCAB_PREFIX,
      content="vocab:{language}:{word} — {translation}",
      metadata has word/translation/difficulty/examples
    - Mastery records: preferences table,
      category=_MASTERY_CATEGORY:{language}, value=word_id, strength=mastery_level
    """

    def __init__(self, memory: SemanticMemory) -> None:
        self.memory = memory

    def add_vocabulary(
        self,
        word_id: str,
        word: str,
        translation: str,
        language: str = "spanish",
        difficulty: str = "beginner",
        *,
        part_of_speech: str = "",
        examples: Optional[list] = None,
    ) -> None:
        """Store a vocabulary word as a fact."""
        content = f"vocab:{language}:{word} — {translation}"
        self.memory.add_fact(
            content,
            confidence=0.9,
            source=_VOCAB_PREFIX,
            fact_id=f"{_VOCAB_PREFIX}_{language}_{word_id}",
            metadata={
                "word_id": word_id,
                "word": word,
                "translation": translation,
                "language": language,
                "difficulty": difficulty,
                "part_of_speech": part_of_speech,
                "examples": examples or [],
            },
        )

    def track_mastery(
        self,
        user_id: str,
        word_id: str,
        mastery_level: float,
        language: str = "spanish",
    ) -> None:
        """Record mastery of a vocabulary word as a preference."""
        self.memory.add_preference(
            category=f"{_MASTERY_CATEGORY}:{language}",
            value=word_id,
            strength=float(mastery_level),
            source="tutor_session",
            user_id=user_id,
            preference_id=f"mastery_{language}_{user_id}_{word_id}",
        )

    def find_unmastered_words(
        self,
        user_id: str,
        difficulty: str = "beginner",
        language: str = "spanish",
        limit: int = 20,
    ) -> list:
        """Return vocabulary words the user has not yet mastered (strength < 0.8)."""
        try:
            conn = self.memory._reader()

            vocab_rows = conn.execute(
                "SELECT id, content, metadata FROM facts WHERE source = ? ORDER BY timestamp ASC",
                (_VOCAB_PREFIX,),
            ).fetchall()

            mastered_rows = conn.execute(
                """
                SELECT value, strength FROM preferences
                WHERE category = ? AND user_id = ? AND strength >= 0.8
                """,
                (f"{_MASTERY_CATEGORY}:{language}", user_id),
            ).fetchall()
            mastered_ids = {r["value"] for r in mastered_rows}

            results = []
            for row in vocab_rows:
                try:
                    meta = json.loads(row["metadata"] or "{}")
                except (json.JSONDecodeError, TypeError):
                    meta = {}
                if meta.get("language") != language:
                    continue
                if meta.get("difficulty") != difficulty:
                    continue
                word_id = meta.get("word_id", "")
                if word_id in mastered_ids:
                    continue
                results.append({
                    "word": meta.get("word", ""),
                    "translation": meta.get("translation", ""),
                    "difficulty": meta.get("difficulty", ""),
                    "part_of_speech": meta.get("part_of_speech", ""),
                    "examples": meta.get("examples", []),
                    "word_id": word_id,
                })
                if len(results) >= limit:
                    break
            return results

        except Exception as exc:
            logger.warning("find_unmastered_words failed: %s", exc)
            return []

    def find_mastered_words(
        self,
        user_id: str,
        language: str = "spanish",
        min_strength: float = 0.8,
    ) -> list:
        """Return word_ids the user has mastered at or above min_strength."""
        try:
            conn = self.memory._reader()
            rows = conn.execute(
                """
                SELECT value as word_id, strength, timestamp FROM preferences
                WHERE category = ? AND user_id = ? AND strength >= ?
                ORDER BY strength DESC
                """,
                (f"{_MASTERY_CATEGORY}:{language}", user_id, min_strength),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.warning("find_mastered_words failed: %s", exc)
            return []

    def find_confused_pairs(self, word: str, language: str = "spanish", limit: int = 5) -> list:
        """Find vocabulary words that are textually similar (FTS approximation).

        True confusion-pair tracking requires graph edges (CONFUSED_WITH).
        This returns FTS-similar words as a usable fallback.
        """
        try:
            results = self.memory.search_generic_memories(word, limit=limit * 3)
            out = []
            for r in results:
                if r.get("source") != _VOCAB_PREFIX:
                    continue
                meta = r.get("metadata", {}) or {}
                if meta.get("language") != language:
                    continue
                if meta.get("word", "").lower() == word.lower():
                    continue
                out.append({
                    "word": meta.get("word", ""),
                    "translation": meta.get("translation", ""),
                    "similarity_score": r.get("match_score", 0.0),
                })
                if len(out) >= limit:
                    break
            return out
        except Exception as exc:
            logger.warning("find_confused_pairs failed: %s", exc)
            return []

    def find_learning_path_for_concept(self, target_concept: str, max_depth: int = 5) -> list:
        return _graph_not_available("find_learning_path_for_concept")


# ---------------------------------------------------------------------------
# File Organizer
# ---------------------------------------------------------------------------

class FileOrganizerHelpers:
    """Semantic helpers for the file organizer project type.

    Photo metadata stored as facts.  Relationship-based operations
    (SIMILAR_TO, PART_OF) require graph storage.
    """

    def __init__(self, memory: SemanticMemory) -> None:
        self.memory = memory

    def add_photo(
        self,
        photo_id: str,
        path: str,
        timestamp: float,
        metadata: dict,
    ) -> None:
        """Store photo metadata as a fact."""
        filename = path.rsplit("/", 1)[-1]
        content = f"photo:{photo_id} path:{path} file:{filename}"
        self.memory.add_fact(
            content,
            confidence=0.9,
            source=_PHOTO_PREFIX,
            fact_id=f"{_PHOTO_PREFIX}_{photo_id}",
            metadata={
                "photo_id": photo_id,
                "path": path,
                "timestamp": timestamp,
                **{k: v for k, v in metadata.items()
                   if isinstance(v, (str, int, float, bool))},
            },
        )

    def find_photos_by_keyword(self, keyword: str, limit: int = 20) -> list:
        """Find photos by FTS search on path/filename."""
        results = self.memory.search_generic_memories(keyword, limit=limit * 2)
        return [
            {
                "path": r.get("metadata", {}).get("path", ""),
                "photo_id": r.get("metadata", {}).get("photo_id", ""),
                "match_score": r.get("match_score", 0.0),
            }
            for r in results if r.get("source") == _PHOTO_PREFIX
        ][:limit]

    def detect_events(self, **_: Any) -> list:
        return _graph_not_available("detect_events")

    def find_duplicates(self, **_: Any) -> list:
        return _graph_not_available("find_duplicates")

    def find_photos_by_person(self, person_name: str) -> list:
        return _graph_not_available("find_photos_by_person")

    def find_photos_by_location(self, country: str) -> list:
        return _graph_not_available("find_photos_by_location")

    def cluster_by_event(self) -> list:
        return _graph_not_available("cluster_by_event")


# ---------------------------------------------------------------------------
# Voice Interface
# ---------------------------------------------------------------------------

class VoiceInterfaceHelpers:
    """Semantic helpers for the voice interface project type.

    Commands stored as facts.  Sequence/frequency tracking (FOLLOWS edges)
    requires graph storage.
    """

    def __init__(self, memory: SemanticMemory) -> None:
        self.memory = memory

    def add_command(
        self,
        command_id: str,
        text: str,
        intent: str,
        entities: dict,
    ) -> None:
        """Store a voice command as a fact."""
        content = f"command:{intent} text:{text}"
        self.memory.add_fact(
            content,
            confidence=0.8,
            source=_COMMAND_PREFIX,
            fact_id=f"{_COMMAND_PREFIX}_{command_id}",
            metadata={"command_id": command_id, "text": text,
                      "intent": intent, "entities": entities},
        )

    def find_commands_by_intent(self, intent: str, limit: int = 10) -> list:
        """Find stored commands matching an intent via FTS."""
        results = self.memory.search_generic_memories(intent, limit=limit * 2)
        return [
            {
                "text": r.get("metadata", {}).get("text", ""),
                "intent": r.get("metadata", {}).get("intent", ""),
                "command_id": r.get("metadata", {}).get("command_id", ""),
                "match_score": r.get("match_score", 0.0),
            }
            for r in results if r.get("source") == _COMMAND_PREFIX
        ][:limit]

    def track_command_sequence(self, *_: Any, **__: Any) -> list:
        return _graph_not_available("track_command_sequence")

    def predict_next_command(self, *_: Any, **__: Any) -> list:
        return _graph_not_available("predict_next_command")

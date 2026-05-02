"""Synthesis layer for Engram — extracts generalizable rules from episode windows.

Reads a window of recent episodes (working + episodic memory) and uses an LLM
pass to extract higher-order procedural memory: rules of the form "when X,
do Y" or "X tends to lead to Y" — patterns that compound across sessions.

Mirrors the Tier 2 Cognitive layer pattern (cognitive.py) but operates on
windows rather than single turns, and produces SynthesisRule + SynthesisRelation
records rather than per-turn facts.

Design choices:
- Manual trigger only (v1) — called via ProjectMemory.synthesize_now()
- Min support threshold (default 3 episodes) prevents fabricated rules
- Confidence-gated writes — rules below threshold are dropped
- Idempotency: window hash is stored; same hash produces no new writes

Storage targets (see semantic_memory.py schema additions):
- synthesized_rules         — the rule records
- synthesized_relations     — typed edges between rules and supporting facts

Engine config in llm_engines.yaml under key 'synthesis' (or fall back to
'tier2_cognitive' if synthesis-specific entry is absent).

Author: Jeffrey Dean
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# --- Constants ----------------------------------------------------------------

_MAX_RULE_LEN = 480           # rules are pithy but longer than facts
_MIN_SUPPORT_DEFAULT = 3      # min episodes that must support a rule
_MIN_CONFIDENCE_DEFAULT = 0.60
_INFERENCE_TIMEOUT = 60.0     # seconds — synthesis can take longer than tier 2

VALID_RELATION_TYPES = frozenset([
    "DERIVED_FROM",       # rule → supporting_episode_id
    "APPLIES_TO",         # rule → fact/preference about a subject
    "SUPERSEDES",         # newer_rule → older_rule
    "RELATES_TO",         # rule ↔ rule (lateral connection)
    "GENERALIZES",        # rule → fact (specific → general)
])


_SYNTHESIS_PROMPT = """\
You are extracting GENERALIZABLE RULES from a window of past activity.

A rule is a pattern that should apply to FUTURE situations, not just describe \
the past.

Good rules:
- "When refactoring SQLite schema, add WAL pragma to all new connections"
- "Vector similarity threshold below 0.4 lets decoy results bleed through"
- "Always run `pip install -e .` after editing pyproject.toml dependencies"

Bad rules (do NOT emit these):
- Restatements of single events: "Fixed the SQLite bug yesterday"
- One-off observations: "User mentioned they like Python"
- Speculation without evidence: "Async is probably better here"

Requirements:
- Each rule MUST be supported by at least {min_support} distinct episodes.
- Cite the supporting episode indices (0-based) in `support_indices`.
- confidence: 0.0-1.0 — how clearly the pattern is established by the support.
- Return ONLY a JSON array. No preamble, no markdown fences.

Output schema per rule:
{{
  "rule": "concise generalizable statement",
  "support_indices": [0, 3, 7],
  "confidence": 0.85
}}

If no rules meet the support threshold, return [].

Episodes (numbered 0..N):
{episodes}

Rules (JSON array):"""


# --- Data structures ----------------------------------------------------------


@dataclass
class SynthesisRule:
    """A generalizable rule extracted from an episode window."""
    rule_text: str
    support_episode_ids: List[str] = field(default_factory=list)
    support_count: int = 0
    confidence: float = 0.7
    source: str = "synthesis"
    timestamp: float = field(default_factory=time.time)

    def stable_id(self, project_id: str = "") -> str:
        """Hash-based ID so re-extraction of same rule is idempotent."""
        norm = re.sub(r"\s+", " ", self.rule_text.strip().lower())
        h = hashlib.sha1(f"{project_id}|{norm}".encode("utf-8")).hexdigest()
        return f"rule_{h[:16]}"

    def to_payload(self, project_id: str = "") -> Dict[str, Any]:
        return {
            "id": self.stable_id(project_id),
            "rule_text": self.rule_text[:_MAX_RULE_LEN],
            "support_episode_ids": list(self.support_episode_ids),
            "support_count": self.support_count,
            "confidence": float(self.confidence),
            "source": self.source,
            "timestamp": float(self.timestamp),
        }


@dataclass
class SynthesisRelation:
    """A typed edge linking synthesis rules to other records."""
    relation_type: str
    subject_id: str        # rule id or fact id
    object_id: str         # rule id or fact id or episode id
    weight: float = 1.0
    source_synthesis_id: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "relation_type": self.relation_type,
            "subject_id": self.subject_id,
            "object_id": self.object_id,
            "weight": float(self.weight),
            "source_synthesis_id": self.source_synthesis_id,
        }


@dataclass
class SynthesisResult:
    """Bundle returned by SynthesisExtractor.extract()."""
    rules: List[SynthesisRule] = field(default_factory=list)
    relations: List[SynthesisRelation] = field(default_factory=list)
    window_hash: str = ""
    extraction_seconds: float = 0.0
    skipped_reason: Optional[str] = None  # populated when no work done

    @property
    def empty(self) -> bool:
        return not self.rules and not self.relations


# --- Extractor ----------------------------------------------------------------


class SynthesisExtractor:
    """LLM-based synthesis pass over an episode window.

    No-op when:
    - engine_config is None
    - the configured model file does not exist
    - the window is too small to support rule extraction

    Args:
        engine_config:  Dict from llm_engines.yaml ('synthesis' or
                        fallback 'tier2_cognitive'). None disables.
        min_support:    Min distinct episodes that must support a rule.
        min_confidence: Rules below this threshold are dropped.
    """

    def __init__(
        self,
        engine_config: Optional[Dict[str, Any]] = None,
        min_support: int = _MIN_SUPPORT_DEFAULT,
        min_confidence: float = _MIN_CONFIDENCE_DEFAULT,
    ):
        self._engine_config = engine_config
        self._min_support = max(1, int(min_support))
        self._min_confidence = float(min_confidence)
        self._engine = None
        self._lock = threading.Lock()
        self._extractions = 0
        self._rules_emitted = 0
        self._rules_dropped_low_support = 0
        self._rules_dropped_low_confidence = 0
        self._errors = 0

        if engine_config is not None:
            self._engine = self._load_engine(engine_config)

    @property
    def enabled(self) -> bool:
        return self._engine is not None

    @property
    def stats(self) -> Dict[str, int]:
        return {
            "extractions": self._extractions,
            "rules_emitted": self._rules_emitted,
            "rules_dropped_low_support": self._rules_dropped_low_support,
            "rules_dropped_low_confidence": self._rules_dropped_low_confidence,
            "errors": self._errors,
        }

    def _load_engine(self, config: Dict[str, Any]) -> Any:
        """Load an inference engine from config. Supports ollama and llama_cpp.

        Returns a thin adapter with generate(prompt, max_tokens, temperature) -> str.
        Returns None on any failure (best-effort — extractor degrades gracefully).
        """
        engine_type = (config.get("type") or "llama_cpp").lower()

        if engine_type == "ollama":
            return self._load_ollama_engine(config)
        else:
            return self._load_llamacpp_engine(config)

    def _load_ollama_engine(self, config: Dict[str, Any]) -> Any:
        """Load an Ollama engine and wrap it in a simple generate() adapter."""
        try:
            from llm_engines.backends.ollama import OllamaEngine
            from llm_engines.contracts.engine import GenerationRequest, ChatMessage

            host = config.get("base_url", "http://localhost:11434")
            # Strip /v1 suffix if present — Ollama native endpoint doesn't use it
            host = host.rstrip("/")
            if host.endswith("/v1"):
                host = host[:-3]

            engine = OllamaEngine(
                model=config["model"],
                host=host,
                think=False,  # disable chain-of-thought for extraction tasks
            )

            class _OllamaAdapter:
                """Thin adapter: generate(prompt, max_tokens, temperature) -> str."""
                def __init__(self, eng):
                    self._eng = eng

                def generate(self, prompt: str, max_tokens: int = 1024,
                             temperature: float = 0.2) -> str:
                    req = GenerationRequest(
                        messages=[ChatMessage(role="user", content=prompt)],
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    resp = self._eng.generate(req)
                    return resp.message.content or ""

            logger.debug(
                "SynthesisExtractor: loaded Ollama engine model=%s host=%s",
                config["model"], host,
            )
            return _OllamaAdapter(engine)

        except ImportError as exc:
            logger.warning("SynthesisExtractor: llm_engines not available: %s", exc)
            return None
        except Exception as exc:
            logger.warning("SynthesisExtractor: Ollama engine load failed: %s — disabled", exc)
            return None

    def _load_llamacpp_engine(self, config: Dict[str, Any]) -> Any:
        """Load a llama.cpp engine (requires gguf_path on disk)."""
        try:
            from pathlib import Path
            from ..engine.llama_cpp_engine import LlamaCppEngine

            model_path = Path(config["gguf_path"]).expanduser()
            if not model_path.exists():
                logger.warning(
                    "SynthesisExtractor: model not found at %s — disabled",
                    model_path,
                )
                return None

            engine = LlamaCppEngine(
                base_url=config.get("base_url", "http://127.0.0.1:8080/v1"),
                api_key=config.get("api_key", "dummy"),
                gguf_path=str(model_path),
                n_gpu_layers=int(config.get("n_gpu_layers", 0)),
                model_name=config.get("model", ""),
                max_context=int(config.get("context_size", 4096)),
            )
            logger.debug("SynthesisExtractor: loaded llama.cpp engine from %s", model_path)
            return engine
        except ImportError:
            logger.warning("SynthesisExtractor: LlamaCppEngine not available — disabled")
            return None
        except Exception as exc:
            logger.warning("SynthesisExtractor: llama.cpp engine load failed: %s — disabled", exc)
            return None

    # --- Public API ---------------------------------------------------------

    def extract(
        self,
        episodes: List[Dict[str, Any]],
        project_id: str = "",
    ) -> SynthesisResult:
        """Run a synthesis pass over an episode window.

        Args:
            episodes: List of dicts; each must have at minimum
                'id' (str) and 'text' (str). Optional 'role', 'timestamp'.
            project_id: Used in rule stable_id hashing for cross-project safety.

        Returns:
            SynthesisResult — possibly empty on no-op or extraction failure.
        """
        result = SynthesisResult()

        if not self.enabled:
            result.skipped_reason = "extractor_disabled"
            return result

        if len(episodes) < self._min_support:
            result.skipped_reason = (
                f"window_too_small ({len(episodes)} < {self._min_support})"
            )
            return result

        result.window_hash = self._hash_window(episodes)
        episodes_text = self._format_episodes(episodes)
        if not episodes_text.strip():
            result.skipped_reason = "empty_episodes"
            return result

        prompt = _SYNTHESIS_PROMPT.format(
            min_support=self._min_support,
            episodes=episodes_text,
        )

        t0 = time.time()
        try:
            response = self._engine.generate(
                prompt,
                max_tokens=self._engine_config.get("max_tokens", 1024),
                temperature=self._engine_config.get("temperature", 0.2),
            )
        except Exception as exc:
            self._errors += 1
            result.skipped_reason = f"inference_failed: {exc}"
            logger.warning("SynthesisExtractor: inference failed: %s", exc)
            return result

        result.extraction_seconds = time.time() - t0
        self._extractions += 1

        raw_rules = self._parse_response(response)
        result.rules, result.relations = self._build_records(
            raw_rules, episodes, project_id
        )
        self._rules_emitted += len(result.rules)
        return result

    # --- Internals ----------------------------------------------------------

    def _format_episodes(self, episodes: List[Dict[str, Any]]) -> str:
        lines = []
        for idx, ep in enumerate(episodes):
            text = (ep.get("text") or ep.get("content") or "").strip()
            if not text:
                continue
            role = (ep.get("role") or "").strip()
            prefix = f"[{idx}]"
            if role:
                prefix += f" {role.capitalize()}:"
            # Truncate per-episode to keep prompt manageable
            if len(text) > 600:
                text = text[:597] + "..."
            lines.append(f"{prefix} {text}")
        return "\n\n".join(lines)

    def _hash_window(self, episodes: List[Dict[str, Any]]) -> str:
        """Stable hash of the window for idempotency checks."""
        ids = "|".join(str(ep.get("id", "")) for ep in episodes)
        return hashlib.sha1(ids.encode("utf-8")).hexdigest()[:16]

    def _parse_response(self, response: str) -> List[Dict[str, Any]]:
        """Tolerant JSON-array parser, mirrors cognitive.py behavior."""
        text = response.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                l for l in lines if not l.strip().startswith("```")
            ).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1 and end > start:
                try:
                    data = json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    logger.debug(
                        "SynthesisExtractor: unparseable JSON: %s",
                        text[:200],
                    )
                    return []
            else:
                return []

        if not isinstance(data, list):
            return []
        return [r for r in data if isinstance(r, dict)]

    def _build_records(
        self,
        raw_rules: List[Dict[str, Any]],
        episodes: List[Dict[str, Any]],
        project_id: str,
    ) -> Tuple[List[SynthesisRule], List[SynthesisRelation]]:
        rules: List[SynthesisRule] = []
        relations: List[SynthesisRelation] = []

        for raw in raw_rules:
            rule_text = (raw.get("rule") or "").strip()
            if not rule_text:
                continue

            support_indices = raw.get("support_indices") or []
            if not isinstance(support_indices, list):
                continue

            # Resolve indices to episode ids
            episode_ids: List[str] = []
            for idx in support_indices:
                if isinstance(idx, int) and 0 <= idx < len(episodes):
                    ep_id = str(episodes[idx].get("id", ""))
                    if ep_id:
                        episode_ids.append(ep_id)

            if len(episode_ids) < self._min_support:
                self._rules_dropped_low_support += 1
                continue

            try:
                confidence = float(raw.get("confidence", 0.7))
            except (TypeError, ValueError):
                confidence = 0.7

            if confidence < self._min_confidence:
                self._rules_dropped_low_confidence += 1
                continue

            rule = SynthesisRule(
                rule_text=rule_text,
                support_episode_ids=episode_ids,
                support_count=len(episode_ids),
                confidence=min(1.0, max(0.0, confidence)),
            )
            rules.append(rule)

            # Emit DERIVED_FROM relations: rule → each supporting episode
            rule_id = rule.stable_id(project_id)
            for ep_id in episode_ids:
                relations.append(
                    SynthesisRelation(
                        relation_type="DERIVED_FROM",
                        subject_id=rule_id,
                        object_id=ep_id,
                        weight=rule.confidence,
                        source_synthesis_id=rule_id,
                    )
                )

        return rules, relations

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
_MAX_TRIGGER_LEN = 200        # skill trigger phrase
_MAX_STEP_LEN = 300           # one procedure step
_MAX_SKILL_STEPS = 10         # cap step list length
_MIN_SUPPORT_DEFAULT = 3      # min episodes that must support a rule or skill
_MIN_CONFIDENCE_DEFAULT = 0.60
_INFERENCE_TIMEOUT = 60.0     # seconds — synthesis can take longer than tier 2

# Lazy import — keeps synthesis.py free of numpy dependency.
def _skill_cls():
    from engram.memory.procedural import Skill
    return Skill

VALID_RELATION_TYPES = frozenset([
    "DERIVED_FROM",       # rule → supporting_episode_id
    "APPLIES_TO",         # rule → fact/preference about a subject
    "SUPERSEDES",         # newer_rule → older_rule
    "RELATES_TO",         # rule ↔ rule (lateral connection)
    "GENERALIZES",        # rule → fact (specific → general)
])


_SYNTHESIS_PROMPT = """\
You are extracting GENERALIZABLE RULES and REUSABLE SKILLS from a window of \
past activity.

=== RULES ===
A rule is a short, actionable pattern: "when X, do Y" or "X leads to Y".

Good rules:
- "When refactoring SQLite schema, add WAL pragma to all new connections"
- "Vector similarity threshold below 0.4 lets decoy results bleed through"
- "Always run `pip install -e .` after editing pyproject.toml dependencies"

Bad rules (do NOT emit):
- Restatements of single events: "Fixed the SQLite bug yesterday"
- One-off observations: "User mentioned they like Python"
- Speculation without evidence: "Async is probably better here"

=== SKILLS ===
A skill is a MULTI-STEP PROCEDURE that can be reused for a class of tasks.
Skills have a trigger phrase (WHEN to use it) and ordered steps (HOW to do it).

Good skills:
- trigger: "when setting up a new SQLite-backed memory layer"
  steps: ["Create table with WAL pragma", "Add FTS5 virtual table",
  "Add INSERT/DELETE/UPDATE triggers to sync FTS", "Verify with PRAGMA integrity_check"]

Bad skills (do NOT emit):
- Single-step procedures (use a rule instead)
- Generic advice with no concrete steps
- Skills supported by only one episode

=== REQUIREMENTS ===
- Every rule and skill MUST be supported by at least {min_support} distinct episodes.
- Cite episode indices (0-based) in support_indices.
- confidence: 0.0-1.0 — how clearly the pattern repeats across the support.
- Return ONLY a JSON object. No preamble, no markdown fences.

Output schema:
{{
  "rules": [
    {{"rule": "concise statement", "support_indices": [0, 3], "confidence": 0.85}}
  ],
  "skills": [
    {{
      "name": "short title (8 words or fewer)",
      "trigger": "when <situation>...",
      "when_to_use": "one sentence explaining context",
      "steps": ["step 1", "step 2", "step 3"],
      "examples": [{{"input": "...", "output": "..."}}],
      "support_indices": [1, 4, 6],
      "confidence": 0.80
    }}
  ]
}}

If no rules or skills meet the support threshold, use empty arrays.

Episodes (numbered 0..N):
{episodes}

Output:"""


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
    skills: List[Any] = field(default_factory=list)   # List[Skill] from procedural.py
    window_hash: str = ""
    extraction_seconds: float = 0.0
    skipped_reason: Optional[str] = None  # populated when no work done

    @property
    def empty(self) -> bool:
        return not self.rules and not self.relations and not self.skills


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
        self._skills_emitted = 0
        self._skills_dropped_low_support = 0
        self._skills_dropped_low_confidence = 0
        self._skills_dropped_bad_format = 0
        self._errors = 0

        if engine_config is not None:
            self._engine = self._load_engine(engine_config)

    def _ensure_counter_fields(self) -> None:
        """Backfill counters for legacy/test construction via __new__."""
        defaults = {
            "_extractions": 0,
            "_rules_emitted": 0,
            "_rules_dropped_low_support": 0,
            "_rules_dropped_low_confidence": 0,
            "_skills_emitted": 0,
            "_skills_dropped_low_support": 0,
            "_skills_dropped_low_confidence": 0,
            "_skills_dropped_bad_format": 0,
            "_errors": 0,
        }
        for name, value in defaults.items():
            if not hasattr(self, name):
                setattr(self, name, value)

    @property
    def enabled(self) -> bool:
        return self._engine is not None

    @property
    def stats(self) -> Dict[str, int]:
        self._ensure_counter_fields()
        return {
            "extractions": self._extractions,
            "rules_emitted": self._rules_emitted,
            "rules_dropped_low_support": self._rules_dropped_low_support,
            "rules_dropped_low_confidence": self._rules_dropped_low_confidence,
            "skills_emitted": self._skills_emitted,
            "skills_dropped_low_support": self._skills_dropped_low_support,
            "skills_dropped_low_confidence": self._skills_dropped_low_confidence,
            "skills_dropped_bad_format": self._skills_dropped_bad_format,
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
        """Load an Ollama engine wrapped in EngramLLMAdapter."""
        try:
            from llm_engines.backends.ollama import OllamaEngine
            from ..adapters.llm_adapter import EngramLLMAdapter

            host = config.get("base_url", "http://localhost:11434").rstrip("/")
            if host.endswith("/v1"):
                host = host[:-3]   # Ollama native endpoint does not use /v1

            engine = OllamaEngine(
                model=config["model"],
                host=host,
                think=False,   # disable chain-of-thought for extraction tasks
            )
            logger.debug(
                "SynthesisExtractor: loaded Ollama engine model=%s host=%s",
                config["model"], host,
            )
            return EngramLLMAdapter(engine)

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
        self._ensure_counter_fields()
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

        raw_rules, raw_skills = self._parse_response(response)
        result.rules, result.relations = self._build_records(
            raw_rules, episodes, project_id
        )
        result.skills = self._build_skill_records(raw_skills, episodes, project_id)
        self._rules_emitted += len(result.rules)
        self._skills_emitted += len(result.skills)
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

    def _parse_response(self, response: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Parse LLM output into (raw_rules, raw_skills).

        Accepts two formats for backward compatibility:
        - New: JSON object  {"rules": [...], "skills": [...]}
        - Legacy: JSON array [...]  (treated as rules only, no skills)
        """
        text = response.strip()
        if text.startswith("```"):
            text = "\n".join(
                l for l in text.splitlines() if not l.strip().startswith("```")
            ).strip()

        def _try_parse(s: str) -> Any:
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                return None

        data = _try_parse(text)

        # Bracket search fallback
        if data is None:
            for open_c, close_c in (("{", "}"), ("[", "]")):
                start = text.find(open_c)
                end = text.rfind(close_c)
                if start != -1 and end > start:
                    data = _try_parse(text[start:end + 1])
                    if data is not None:
                        break

        if data is None:
            logger.debug("SynthesisExtractor: unparseable JSON: %s", text[:200])
            return [], []

        # New format: {"rules": [...], "skills": [...]}
        if isinstance(data, dict):
            raw_rules = [r for r in data.get("rules", []) if isinstance(r, dict)]
            raw_skills = [s for s in data.get("skills", []) if isinstance(s, dict)]
            return raw_rules, raw_skills

        # Legacy format: plain array → rules only
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)], []

        return [], []

    def _build_records(
        self,
        raw_rules: List[Dict[str, Any]],
        episodes: List[Dict[str, Any]],
        project_id: str,
    ) -> Tuple[List[SynthesisRule], List[SynthesisRelation]]:
        self._ensure_counter_fields()
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

    def _build_skill_records(
        self,
        raw_skills: List[Dict[str, Any]],
        episodes: List[Dict[str, Any]],
        project_id: str,
    ) -> List[Any]:
        """Parse raw skill dicts into Skill objects with support validation."""
        self._ensure_counter_fields()
        Skill = _skill_cls()
        skills: List[Any] = []

        for raw in raw_skills:
            # --- Required fields ---
            name = (raw.get("name") or "").strip()
            trigger = (raw.get("trigger") or "").strip()
            steps_raw = raw.get("steps") or []

            if not name or not trigger:
                self._skills_dropped_bad_format += 1
                continue

            if not isinstance(steps_raw, list):
                self._skills_dropped_bad_format += 1
                continue

            steps = [
                str(s).strip()[:_MAX_STEP_LEN]
                for s in steps_raw
                if str(s).strip()
            ][:_MAX_SKILL_STEPS]

            if len(steps) < 2:
                # Single-step → use a rule instead
                self._skills_dropped_bad_format += 1
                continue

            # --- Support validation (same rule as rules) ---
            support_indices = raw.get("support_indices") or []
            if not isinstance(support_indices, list):
                self._skills_dropped_low_support += 1
                continue

            episode_ids: List[str] = []
            for idx in support_indices:
                if isinstance(idx, int) and 0 <= idx < len(episodes):
                    ep_id = str(episodes[idx].get("id", ""))
                    if ep_id:
                        episode_ids.append(ep_id)

            if len(episode_ids) < self._min_support:
                self._skills_dropped_low_support += 1
                continue

            try:
                confidence = float(raw.get("confidence", 0.7))
            except (TypeError, ValueError):
                confidence = 0.7

            if confidence < self._min_confidence:
                self._skills_dropped_low_confidence += 1
                continue

            # --- Optional fields ---
            when_to_use = (raw.get("when_to_use") or "").strip()
            examples_raw = raw.get("examples") or []
            examples = [
                e for e in examples_raw
                if isinstance(e, dict) and ("input" in e or "output" in e)
            ][:3]

            skill = Skill(
                name=name[:80],
                trigger=trigger[:_MAX_TRIGGER_LEN],
                steps=steps,
                when_to_use=when_to_use[:400],
                examples=examples,
                support_episode_ids=episode_ids,
                confidence=min(1.0, max(0.0, confidence)),
                project_id=project_id,
                metadata={"source": "synthesis"},
            )
            skills.append(skill)

        return skills


# ---------------------------------------------------------------------------
# Module-level helpers extracted from ProjectMemory
# ---------------------------------------------------------------------------

import logging as _syn_logger_mod
_syn_log = _syn_logger_mod.getLogger(__name__)


def load_engine_config():
    """Load 'synthesis' engine config, falling back to 'tier2_cognitive'."""
    try:
        from .engine.config_loader import load_config
        engines = (load_config().get("engines") or {})
        return engines.get("synthesis") or engines.get("tier2_cognitive")
    except Exception as exc:
        _syn_log.debug("load_engine_config: %s", exc)
        return None


def build_synthesis_block(
    semantic,
    project_id: str,
    query: str,
    token_counter,
    max_rules: int = 3,
    max_tokens: int = 300,
    min_match_score: float = -5.0,
) -> str:
    """Return a formatted block of synthesis rules matching query, or \'\'.

    Extracted from ProjectMemory._build_synthesis_block().
    """
    if semantic is None or not query or not query.strip():
        return ""
    try:
        hits = semantic.search_synthesis_rules(
            query=query,
            project_id=project_id,
            limit=max_rules * 3,
            min_confidence=0.6,
        )
    except Exception as exc:
        _syn_log.debug("build_synthesis_block: search failed: %s", exc)
        return ""
    if not hits:
        return ""
    hits = [h for h in hits if h.get("match_score", -999) >= min_match_score]
    if not hits:
        return ""
    lines = []
    tokens_used = 0
    for hit in hits[:max_rules]:
        rule_text = hit.get("rule_text", "").strip()
        if not rule_text:
            continue
        rule_tokens = max(1, token_counter(rule_text))
        if tokens_used + rule_tokens > max_tokens:
            break
        lines.append(f"- {rule_text}")
        tokens_used += rule_tokens
    return "\n".join(lines)


def run_synthesis(
    pm,
    window_size: int = 50,
    days_back: int = 30,
    min_support: int = 3,
    min_confidence: float = 0.60,
) -> dict:
    """Run a synthesis pass over recent episodes and write rules to semantic memory.

    Extracted from ProjectMemory.synthesize_now(). Accepts the ProjectMemory
    instance as ``pm`` for the initial extraction; will be refactored to
    explicit dependencies in a later pass.
    """
    result = {
        "rules_written": 0,
        "rules_skipped": 0,
        "relations_written": 0,
        "skills_written": 0,
        "skills_skipped": 0,
        "window_size": 0,
        "extraction_seconds": 0.0,
        "skipped_reason": None,
    }

    if pm.episodic is None:
        result["skipped_reason"] = "episodic_layer_unavailable"
        _syn_log.warning("run_synthesis: episodic layer not available")
        return result
    if pm.semantic is None:
        result["skipped_reason"] = "semantic_layer_unavailable"
        _syn_log.warning("run_synthesis: semantic layer not available")
        return result

    engine_config = load_engine_config()
    if engine_config is None:
        result["skipped_reason"] = "no_engine_config"
        _syn_log.warning(
            "run_synthesis: no 'synthesis' or 'tier2_cognitive' engine "
            "configured in llm_engines.yaml"
        )
        return result

    extractor = SynthesisExtractor(
        engine_config=engine_config,
        min_support=min_support,
        min_confidence=min_confidence,
    )
    if not extractor.enabled:
        result["skipped_reason"] = "extractor_disabled"
        return result

    episodes = pm.episodic.get_recent_episodes(
        n=window_size, days_back=days_back, project_id=pm.project_id,
    )
    episode_dicts = [ep.to_dict() for ep in episodes]
    result["window_size"] = len(episode_dicts)

    synth = extractor.extract(episode_dicts, project_id=pm.project_id)
    result["extraction_seconds"] = synth.extraction_seconds

    if synth.skipped_reason:
        result["skipped_reason"] = synth.skipped_reason
        return result

    for rule in synth.rules:
        payload = rule.to_payload(project_id=pm.project_id)
        written = pm.semantic.store_synthesis_rule(payload, project_id=pm.project_id)
        if written:
            result["rules_written"] += 1
        else:
            result["rules_skipped"] += 1

    for rel in synth.relations:
        pm.semantic.store_synthesis_relation(rel.to_payload(), project_id=pm.project_id)
        result["relations_written"] += 1

    for skill in synth.skills:
        skill.project_id = pm.project_id
        emb = pm.embedding_service.embed(skill.trigger)
        if emb is not None:
            skill.embedding = emb
        if pm.procedural.get_skill(skill.skill_id) is None:
            pm.procedural.add_skill(skill)
            result["skills_written"] += 1
        else:
            result["skills_skipped"] += 1

    _syn_log.info(
        "run_synthesis: project=%s rules_written=%d skipped=%d "
        "relations=%d skills_written=%d window=%d elapsed=%.1fs",
        pm.project_id, result["rules_written"], result["rules_skipped"],
        result["relations_written"], result["skills_written"],
        result["window_size"], result["extraction_seconds"],
    )
    return result

"""
Tutor Session Orchestrator

Main session management class that integrates:
- Hardware-adaptive engine management
- Engram memory through a narrow tutor-owned protocol
- Graceful shutdown integration
- Cost tracking
- Session planning and summaries

Author: Jeff
"""

import time
import json
import re
from types import SimpleNamespace
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

# Import our modules (relative imports)
from .memory_backend import TutorMemoryBackend, create_memory_backend
from .interop import (
    describe_language_tutor,
    explanation_to_interop_result,
    start_result_to_interop_result,
    tutor_response_to_interop_result,
)
from .session_store import SessionStore
from .drills.drill_system import DrillSystem

# Import our strategy system (relative import)
from .engine_manager import EngineManager, CostTracker


@dataclass
class TutorResponse:
    """Response from tutor to user message."""

    text: str
    corrections: Optional[List[dict]] = None
    new_vocabulary: Optional[List[dict]] = None
    metadata: Optional[dict] = None


class SessionState(Enum):
    """Session state machine."""

    IDLE = "idle"
    PLANNING = "planning"
    WARMUP = "warmup"
    CONVERSATION = "conversation"
    DRILL = "drill"
    EXPLANATION = "explanation"
    PAUSED = "paused"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    ERROR = "error"


class TutorSession:
    """
    Main session orchestrator for language tutoring.

    Manages:
    - Engine lifecycle (planner/executor)
    - Memory via the public Engram API
    - Session planning and summaries
    - Cost tracking
    - Graceful shutdown
    """

    def __init__(
        self,
        language: str,
        strategy: Dict[str, Any],
        base_dir: Path,
        session_id: Optional[str] = None,
        memory_backend: Optional[str] = None,
    ):
        """Initialize tutoring session."""
        self.language = language
        self.strategy = strategy
        self.base_dir = base_dir
        self.session_id = session_id or self._generate_session_id()

        # Load language profile
        from .config import get_language_profile

        self.profile = get_language_profile(language)

        # Initialize engine manager
        self.engines = EngineManager(strategy)

        # Get executor (keep loaded)
        self.executor = self.engines.get_executor()

        # Initialize memory with strategy-aware engine
        self.memory_backend = (
            (memory_backend or strategy.get("memory_backend") or "engram").strip().lower()
        )
        self.memory = self._init_memory()

        # Cost tracking (if cloud-based)
        if strategy["cost_per_session"] > 0:
            self.cost_tracker = CostTracker(strategy)
        else:
            self.cost_tracker = None

        # Session state
        self.state = SessionState.IDLE
        self.current_plan: Optional[Dict] = None
        self.start_time = time.time()
        self.exchange_count = 0
        # Eval metrics
        self.corrections_count = 0
        self.vocab_learned: List[dict] = []

        # Session persistence (survives restarts, feeds planner)
        self.store = SessionStore(db_path=base_dir / "memory" / f"{language}_sessions.db")
        self.store.start_session(
            session_id=self.session_id,
            language=language,
        )

        # Drill system (replaces pseudocode stub)
        self.drills = DrillSystem(
            language=language,
            memory=self.memory,
            engine=self.executor,
            store=self.store,
        )
        # Cache the active drill question so check_drill can validate it
        self._current_drill: Optional[Dict] = None

        print(f"\n✓ Session initialized: {self.session_id}")
        print(f"  Language: {language}")
        print(f"  Strategy: {strategy['name']}")
        print(f"  Memory backend: {self.memory_backend}")
        print(f"  Surprise filter: {'Enabled' if strategy['surprise_filter'] else 'Disabled'}")

    def _generate_session_id(self) -> str:
        """Generate session ID with timestamp."""
        return f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def _init_memory(self) -> TutorMemoryBackend:
        """Initialize the selected memory backend with strategy-aware engine support."""
        memory_engine = self.engines.get_memory_engine()

        if self.memory_backend == "engram" and memory_engine is None:
            print("ℹ️  Surprise filter disabled (cloud executor mode)")

        return create_memory_backend(
            backend_name=self.memory_backend,
            language=self.language,
            base_dir=self.base_dir,
            session_id=self.session_id,
            memory_engine=memory_engine,
        )

    async def start(self, duration_minutes: int = 30) -> Dict[str, Any]:
        """Start session with planning phase."""

        class SessionPlan(BaseModel):
            warmup_topic: str = Field(description="Topic for warmup conversation")
            focus_areas: List[str] = Field(description="2-3 grammar/vocabulary areas to practice")
            drill_type: str = Field(description="Type of drill")
            new_content: List[str] = Field(description="New vocabulary or concepts")
            estimated_minutes: Dict[str, int] = Field(description="Time allocation")

        self.state = SessionState.PLANNING
        print(f"\n📋 Planning your {duration_minutes}-minute lesson...")

        planner = self.engines.get_planner()

        # Retrieve past session summaries from memory first, then fall back
        # to the durable SessionStore so resume behaviour survives across
        # backends and lighter memory configurations.
        past_sessions = []
        try:
            past_sessions = self.memory.search_episodes(
                query="session summary",
                n=3,
                min_importance=0.9,
            )
        except Exception:
            past_sessions = []

        if len(past_sessions) < 3:
            try:
                seen = {
                    getattr(item, "text", str(item)).strip()
                    for item in past_sessions
                    if getattr(item, "text", str(item)).strip()
                }
                for row in self.store.get_session_history(self.language, limit=5):
                    summary = str(row.get("summary", "")).strip()
                    if not summary or summary in seen:
                        continue
                    past_sessions.append(
                        SimpleNamespace(text=summary, metadata={"source": "session_store", **row})
                    )
                    seen.add(summary)
                    if len(past_sessions) >= 3:
                        break
            except Exception:
                pass

        # Retrieve unmastered vocabulary from semantic layer via LanguageTutorHelpers.
        # find_unmastered_words() queries VocabularyWord nodes not yet MASTERED by user.
        # "all" is not a valid difficulty — try each level and merge.
        unmastered = []
        try:
            if self.memory.helpers is not None:
                seen_words: set = set()
                for diff in ("beginner", "intermediate", "advanced"):
                    rows = self.memory.helpers.find_unmastered_words(
                        user_id="default",
                        difficulty=diff,
                    )
                    for row in rows:
                        w = row.get("word", "")
                        if w and w not in seen_words:
                            unmastered.append(w)
                            seen_words.add(w)
                    if len(unmastered) >= 10:
                        break
        except Exception:
            pass

        planning_prompt = self._build_planning_prompt(
            duration_minutes=duration_minutes,
            past_sessions=past_sessions,
            unmastered=unmastered,
            weaknesses=self.store.get_weaknesses(self.language),
        )

        if hasattr(planner, "generate_structured"):
            try:
                plan = planner.generate_structured(
                    prompt=planning_prompt,
                    response_model=SessionPlan,
                    system_prompt=self.profile.system_prompt,
                )
                plan_dict = plan.model_dump()
            except Exception as e:
                print(f"⚠️  Structured generation failed: {e}")
                plan_text = planner.generate(
                    prompt=planning_prompt,
                    system_prompt=self.profile.system_prompt,
                    max_tokens=1000,
                )
                plan_dict = {"text": plan_text}
        else:
            plan_text = planner.generate(
                prompt=planning_prompt,
                system_prompt=self.profile.system_prompt,
                max_tokens=1000,
            )
            plan_dict = {"text": plan_text}

        self.engines.unload_planner()

        self.current_plan = plan_dict
        self.state = SessionState.WARMUP

        print("✓ Plan ready!")

        return {
            "plan": plan_dict,
            "greeting": self.profile.greeting,
            "session_id": self.session_id,
        }

    async def start_interop(self, duration_minutes: int = 30):
        result = await self.start(duration_minutes=duration_minutes)
        return start_result_to_interop_result(self, result)

    async def handle_text(self, user_input: str) -> TutorResponse:
        """Handle text message from user."""

        self.exchange_count += 1
        self.state = SessionState.CONVERSATION

        # Add user turn to working memory; triggers ingestion pipeline
        self.memory.add_turn("user", user_input)

        # Build memory-enriched prompt: injects working + episodic + semantic
        # context with automatic token budgeting and pressure valve.
        # Note: system_prompt lives on the executor, not the memory engine,
        # so we pass it separately to executor.generate().
        prompt_result = self.memory.build_prompt(user_message=user_input)

        # Prepend plan focus to prompt if available
        plan_prefix = ""
        if self.current_plan and isinstance(self.current_plan, dict):
            focus = self.current_plan.get("focus_areas", [])
            if focus:
                plan_prefix = f"[Session focus: {', '.join(focus)}]\n\n"

        full_prompt = (
            plan_prefix + prompt_result["prompt"] if plan_prefix else prompt_result["prompt"]
        )

        response_text = self.executor.generate(
            prompt=full_prompt,
            system_prompt=self.profile.system_prompt,
            max_tokens=300,
        )

        # Store assistant turn; triggers ingestion pipeline (surprise-gated episodic store)
        self.memory.add_turn("assistant", response_text)

        # Index exchange into semantic graph using zero-cost TF-IDF extraction
        try:
            self.memory.index_text(f"User: {user_input}\nAssistant: {response_text}")
        except Exception:
            pass

        # Extract corrections and vocabulary, persist to semantic layer
        corrections = self._extract_corrections(user_input, response_text)
        new_vocab = self._extract_new_vocabulary(response_text)
        self._update_semantic_memory(new_vocab, corrections)

        # Update eval counters
        self.corrections_count += len(corrections)
        self.vocab_learned.extend(new_vocab)

        return TutorResponse(
            text=response_text,
            corrections=corrections,
            new_vocabulary=new_vocab,
            metadata={
                "state": self.state.value,
                "compressed": prompt_result.get("compressed", False),
                "prompt_tokens": prompt_result.get("prompt_tokens", 0),
                "memory_tokens": prompt_result.get("memory_tokens", 0),
            },
        )

    async def handle_text_interop(self, user_input: str):
        response = await self.handle_text(user_input)
        return tutor_response_to_interop_result(self, response, user_message=user_input)

    async def end_session(self) -> Dict[str, Any]:
        """End session with summary generation."""

        self.state = SessionState.SUMMARIZING
        duration = (time.time() - self.start_time) / 60

        print(f"\n📊 Generating session summary ({duration:.1f} minutes)...")

        planner = self.engines.get_planner()

        turns = []
        try:
            turns = self.memory.get_recent_turns(n=100)
        except Exception:
            pass

        summary_prompt = self._build_summary_prompt(
            plan=self.current_plan,
            turns=turns,
        )

        summary = planner.generate(
            prompt=summary_prompt,
            system_prompt="You are summarizing a language learning session.",
            max_tokens=500,
        )

        # Store summary with high importance, bypassing surprise filter
        try:
            self.memory.store_episode(
                text=summary,
                metadata={
                    "type": "session_summary",
                    "language": self.language,
                    "session_id": self.session_id,
                },
                importance=0.95,
                bypass_filter=True,
            )
        except Exception as e:
            print(f"⚠️  Failed to store summary: {e}")

        # Index summary into semantic graph
        try:
            self.memory.index_text(summary)
        except Exception:
            pass

        # Run lifecycle maintenance: forgetting policy + neural consolidation.
        # Promotes high-importance and high-affinity episodes to semantic memory,
        # and archives stale low-value episodes to cold storage.
        try:
            self.memory.run_lifecycle_maintenance()
        except Exception as e:
            print(f"⚠️  Lifecycle maintenance error: {e}")

        self.engines.unload_planner()

        drill_accuracy = self.drills.get_session_accuracy()

        stats = {
            "total_turns": len(turns),
            "session_duration": f"{duration:.1f} minutes",
            "exchanges": self.exchange_count,
            "corrections_made": self.corrections_count,
            "new_vocabulary": len(self.vocab_learned),
            "drill_accuracy": drill_accuracy,
        }

        # Persist to SessionStore so historical data is available for future planners
        self.store.complete_session(
            self.session_id,
            exchanges=self.exchange_count,
            corrections_made=self.corrections_count,
            vocab_learned=len(self.vocab_learned),
            drill_accuracy=drill_accuracy,
            duration_minutes=duration,
            summary=summary,
        )
        for item in self.vocab_learned:
            self.store.log_vocab(
                self.session_id,
                self.language,
                item.get("word", ""),
                item.get("translation", ""),
            )

        self.state = SessionState.COMPLETED
        print("✓ Session summary generated")

        return {
            "summary": summary,
            "statistics": stats,
        }

    def _build_planning_prompt(
        self,
        duration_minutes: int,
        past_sessions: list,
        unmastered: list,
        weaknesses: Optional[list] = None,
    ) -> str:
        """Build prompt for session planning."""

        prompt = f"Plan a {duration_minutes}-minute {self.profile.name} tutoring session.\n\nStudent context:\n"

        if past_sessions:
            prompt += "\nPrevious sessions:\n"
            for session in past_sessions[:3]:
                content = getattr(session, "text", str(session))
                prompt += f"- {content[:200]}...\n"

        if weaknesses:
            prompt += "\nRecent mistake patterns (prioritise these):\n"
            for w in weaknesses[:5]:
                examples = ", ".join(w.get("examples", [])[:2])
                prompt += (
                    f"- {w['error_type']}: {w['count']} times"
                    + (f" (e.g. {examples})" if examples else "")
                    + "\n"
                )

        if unmastered:
            prompt += "\nVocabulary to revisit:\n"
            for word in unmastered[:10]:
                prompt += f"- {word}\n"

        # Suggest a concrete warmup starter from the profile
        starter = self.profile.get_random_starter()
        prompt += f'\nSuggested warmup opener: "{starter}"\n'

        prompt += """
Create a balanced lesson plan with:
1. Warmup topic (conversational, use the opener above or a similar one)
2. 2-3 focus areas (grammar/vocabulary — address weakness patterns above first)
3. Drill type (irregular_verbs_preterite, irregular_verbs_imperfect, reflexive_verbs, prepositions, sentence_dictation, listening_comprehension, or mixed_review)
4. New content to introduce
5. Time allocation

Format as JSON matching the SessionPlan schema.
"""
        return prompt

    def _build_summary_prompt(
        self,
        plan: Optional[Dict],
        turns: list,
    ) -> str:
        """Build prompt for session summary."""

        prompt = f"Summarize this {self.profile.name} tutoring session.\n\nPlanned objectives:\n"

        if plan and isinstance(plan, dict):
            focus = plan.get("focus_areas", [])
            prompt += ", ".join(focus) if focus else "General conversation"
        else:
            prompt += "General conversation"

        prompt += "\n\nConversation:\n"

        for turn in turns[:50]:
            role = getattr(turn, "role", "unknown")
            content = getattr(turn, "content", str(turn))
            prompt += f"{role}: {content}\n"

        prompt += """
Provide a summary including:
1. What was practiced (grammar, vocabulary, topics)
2. Student's strengths shown
3. Areas for improvement
4. Mistakes corrected
5. New vocabulary learned
6. Recommendations for next session
"""
        return prompt

    def _update_semantic_memory(self, vocab: List[dict], corrections: List[dict] = None) -> None:
        """Write vocabulary and corrections into the semantic graph.

        Vocabulary: uses helpers.add_vocabulary() → VocabularyWord nodes.
        Corrections: writes Mistake nodes + MADE_MISTAKE edges from User "default".

        Schema facts (from semantic_schema.py / semantic_helpers.py):
          - VocabularyWord: id, word, language, translation, difficulty, part_of_speech, examples
          - Mistake:        id, incorrect, correct, error_type, frequency, last_occurred
          - MASTERED:       User → VocabularyWord  (mastery_level, last_practiced)
          - MADE_MISTAKE:   User → Mistake          (timestamp)
        """
        import time as _time

        helpers = self.memory.helpers  # LanguageTutorHelpers or None
        semantic = self.memory.semantic  # SemanticMemory or None

        # --- Vocabulary ---
        for item in vocab:
            word = item.get("word", "")
            translation = item.get("translation", "")
            if not (word and translation):
                continue
            if helpers is not None:
                try:
                    word_id = f"{self.language}_{word.lower().replace(' ', '_')}"
                    helpers.add_vocabulary(
                        word_id=word_id,
                        word=word,
                        translation=translation,
                        language=self.language,
                    )
                except Exception:
                    pass

        # --- Corrections → Mistake nodes + MADE_MISTAKE edges ---
        if corrections and semantic is not None:
            # Ensure the "default" User node exists (idempotent via add_node's upsert)
            try:
                semantic.add_node(
                    "User",
                    "default",
                    {
                        "name": "default",
                        "created": _time.time(),
                        "metadata": "{}",
                    },
                )
            except Exception:
                pass

            for item in corrections:
                error = item.get("error", "")
                correction = item.get("correction", "")
                explanation = item.get("explanation", "")
                if not (error and correction):
                    continue
                # Log to SessionStore for historical weakness analysis
                try:
                    self.store.log_mistake(
                        self.session_id,
                        self.language,
                        error,
                        correction,
                        error_type=explanation[:80] if explanation else "grammar",
                    )
                except Exception:
                    pass
                # Write to Engram semantic graph
                try:
                    import hashlib

                    mistake_id = (
                        "mistake_"
                        + hashlib.sha256(f"{self.language}_{error}".encode()).hexdigest()[:12]
                    )
                    semantic.add_node(
                        "Mistake",
                        mistake_id,
                        {
                            "incorrect": error[:200],
                            "correct": correction[:200],
                            "error_type": explanation[:200] if explanation else "grammar",
                            "frequency": 1,
                            "last_occurred": _time.time(),
                        },
                    )
                    semantic.add_relationship(
                        "User",
                        "default",
                        "Mistake",
                        mistake_id,
                        "MADE_MISTAKE",
                        {"timestamp": _time.time()},
                    )
                except Exception:
                    pass

    def _extract_json_list(self, raw: str) -> list:
        """Extract a JSON array from an LLM response string.

        Tries direct parse first, then regex extraction of the first [...] block.
        Returns empty list on any failure.
        """
        raw = raw.strip()
        # Strip markdown fences
        raw = re.sub(r"^```[a-z]*\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"```\s*$", "", raw, flags=re.MULTILINE)
        raw = raw.strip()
        try:
            result = json.loads(raw)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
        # Extract first [...] block
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass
        return []

    def _extract_corrections(self, user_input: str, response: str) -> List[dict]:
        """Extract grammar/vocabulary corrections from the exchange.

        Calls executor with a tightly-scoped prompt. Returns list of
        {error: str, correction: str, explanation: str}.
        Returns [] if no corrections or extraction fails.
        """
        # Skip if response shows no correction happened
        correction_signals = ["corrección", "correction", "error", "debería", "should be"]
        if not any(sig.lower() in response.lower() for sig in correction_signals):
            return []

        prompt = (
            f"Analyze this language exchange. Extract ONLY explicit corrections made.\n\n"
            f"User said: {user_input}\n"
            f"Tutor responded: {response}\n\n"
            f"Return a JSON array of corrections. Each item must have exactly these keys:\n"
            f'  "error": the incorrect form used\n'
            f'  "correction": the correct form\n'
            f'  "explanation": one sentence why\n\n'
            f"If no corrections were made, return []. "
            f"Return ONLY the JSON array, no other text."
        )

        try:
            raw = self.executor.generate(
                prompt=prompt,
                system_prompt="You extract language corrections as JSON. No prose.",
                max_tokens=300,
            )
            return self._extract_json_list(raw)
        except Exception:
            return []

    def _extract_new_vocabulary(self, response: str) -> List[dict]:
        """Extract new vocabulary introduced in the tutor's response.

        Returns list of {word: str, translation: str, part_of_speech: str}.
        Returns [] if no new vocabulary or extraction fails.
        """
        # Quick heuristic: skip if response is very short
        if len(response) < 80:
            return []

        prompt = (
            f"Extract new {self.profile.name} vocabulary introduced in this tutor response.\n\n"
            f"Tutor: {response}\n\n"
            f"Return a JSON array. Each item must have:\n"
            f'  "word": the {self.profile.name} word or phrase\n'
            f'  "translation": English translation\n'
            f'  "part_of_speech": noun/verb/adjective/phrase/etc\n\n'
            f"Only include vocabulary clearly being taught or introduced. "
            f"If none, return []. Return ONLY the JSON array."
        )

        try:
            raw = self.executor.generate(
                prompt=prompt,
                system_prompt="You extract vocabulary as JSON. No prose.",
                max_tokens=400,
            )
            return self._extract_json_list(raw)
        except Exception:
            return []

    async def explain(self, text: str, question: Optional[str] = None) -> str:
        """Generate a grammar explanation using the planner (larger) model.

        Loaded on demand and unloaded immediately after to free VRAM.
        Falls back to executor if planner load fails.
        """
        q_text = question or f"Explain the grammar in: {text}"
        prompt = (
            f"A student learning {self.profile.name} has a grammar question.\n\n"
            f"Text or error: {text}\n"
            f"Question: {q_text}\n\n"
            f"Give a clear, concise explanation (3–6 sentences). "
            f"Use simple terminology. Include a corrected example if relevant."
        )
        planner = None
        try:
            planner = self.engines.get_planner()
            explanation = planner.generate(
                prompt=prompt,
                system_prompt=self.profile.system_prompt,
                max_tokens=400,
            )
        except Exception:
            # Planner unavailable — fall back to executor
            explanation = self.executor.generate(
                prompt=prompt,
                system_prompt=self.profile.system_prompt,
                max_tokens=400,
            )
        finally:
            if planner is not None:
                self.engines.unload_planner()

        return explanation

    async def explain_interop(self, text: str, question: Optional[str] = None):
        explanation = await self.explain(text, question)
        return explanation_to_interop_result(
            self, text=text, question=question, explanation=explanation
        )

    def get_capability_descriptor(self):
        return describe_language_tutor(
            language=self.language,
            memory_backend=self.memory_backend,
            strategy_name=self.strategy.get("name", "unknown"),
        )

    def get_drill(self, drill_type: Optional[str] = None) -> Dict[str, Any]:
        """Return a drill question for the current session.

        If drill_type is None or 'auto', the DrillSystem recommends one
        based on the student's recent mistake history.
        """
        if not drill_type or drill_type == "auto":
            drill_type = self.drills.recommend_drill_type()

        self.state = SessionState.DRILL
        question = self.drills.get_question(drill_type)

        # Cache as plain dict so it survives JSON round-trips
        self._current_drill = {
            "question_id": question.question_id,
            "drill_type": question.drill_type,
            "prompt": question.prompt,
            "correct_answer": question.correct_answer,
            "context": question.context,
            "hint": question.hint,
            "auto_play_tts": question.auto_play_tts,
        }
        return self._current_drill

    def check_drill(self, user_answer: str) -> Dict[str, Any]:
        """Check the user's answer against the cached drill question.

        Returns the DrillResult as a dict plus updated session drill stats.
        Also logs mistakes to SessionStore and Engram semantic layer.
        """
        if self._current_drill is None:
            return {
                "error": "No active drill question. Call get_drill first.",
                "correct": False,
            }

        from .drills.drill_system import DrillQuestion

        q = DrillQuestion(
            question_id=self._current_drill["question_id"],
            drill_type=self._current_drill["drill_type"],
            prompt=self._current_drill["prompt"],
            correct_answer=self._current_drill["correct_answer"],
            context=self._current_drill.get("context", ""),
            hint=self._current_drill.get("hint", ""),
        )

        result = self.drills.check_answer(q, user_answer)

        # Persist mistakes through the same pipeline as conversation corrections
        if not result.correct:
            self._update_semantic_memory(
                vocab=[],
                corrections=[
                    {
                        "error": user_answer,
                        "correction": result.correct_answer,
                        "explanation": f"drill:{q.drill_type}",
                    }
                ],
            )

        self._current_drill = None  # Consumed
        self.state = SessionState.CONVERSATION

        return {
            "correct": result.correct,
            "accuracy": result.accuracy,
            "user_answer": result.user_answer,
            "correct_answer": result.correct_answer,
            "feedback": result.feedback,
            "drill_type": result.drill_type,
            "drill_stats": self.drills.get_session_stats(),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics."""
        duration = (time.time() - self.start_time) / 60
        return {
            "session_id": self.session_id,
            "language": self.language,
            "duration_minutes": duration,
            "exchanges": self.exchange_count,
            "cost_per_session": self.strategy["cost_per_session"],
            "memory_backend": self.memory_backend,
            "memory": self.memory.get_stats(),
        }

    def get_eval_metrics(self) -> Dict[str, Any]:
        """Return structured evaluation metrics for this session.

        Used as the concrete integration test output for Engram:
          - corrections made (Engram CORRECTED relations stored)
          - vocabulary learned (Engram LEARNED relations stored)
          - exchange count (proxy for retention/engagement)
        """
        return {
            "session_id": self.session_id,
            "language": self.language,
            "exchanges": self.exchange_count,
            "corrections_made": self.corrections_count,
            "vocab_learned": len(self.vocab_learned),
            "vocab_detail": self.vocab_learned,
            "duration_minutes": round((time.time() - self.start_time) / 60, 1),
        }

    def close(self):
        """Release all resources."""
        self.memory.close()
        self.engines.shutdown()
        print(f"✓ Session {self.session_id} closed")

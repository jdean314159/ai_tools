"""
Tutor Session Orchestrator

Main session management class that integrates:
- Hardware-adaptive engine management
- ProjectMemory with surprise filter (when available)
- Graceful shutdown integration
- Cost tracking
- Session planning and summaries

Uses memory-rag and llm-engine APIs.

Author: Jeff
"""

import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

# Import from our libraries
from memory_rag import (
    ProjectMemory,
    ProjectType,
    TokenBudget,
)

from llm_engine import LLMEngine

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
    - Memory (working/episodic/semantic)
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
        
        print(f"\n✓ Session initialized: {self.session_id}")
        print(f"  Language: {language}")
        print(f"  Strategy: {strategy['name']}")
        print(f"  Surprise filter: {'Enabled' if strategy['surprise_filter'] else 'Disabled'}")
    
    def _generate_session_id(self) -> str:
        """Generate session ID with timestamp."""
        return f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    def _init_memory(self) -> ProjectMemory:
        """Initialize ProjectMemory with strategy-aware engine."""
        # Get memory engine (may be None for cloud)
        memory_engine = self.engines.get_memory_engine()
        
        if memory_engine is None:
            print("ℹ️  Surprise filter disabled (cloud executor mode)")
        
        # Initialize ProjectMemory
        memory = ProjectMemory(
            project_id=f"{self.language}_tutor",
            project_type=ProjectType.LANGUAGE_TUTOR,
            base_dir=self.base_dir / "memory",
            llm_engine=memory_engine,
            session_id=self.session_id,
            token_budget=TokenBudget(
                working=1000,
                episodic=800,
                semantic=400,
            ),
        )
        
        return memory
    
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
        
        # Get planner engine
        planner = self.engines.get_planner()
        
        # Get context from memory
        past_sessions = []
        try:
            past_sessions = self.memory.episodic.search(
                query="session summary",
                filter_metadata={"type": "session_summary"},
                limit=3,
            )
        except:
            pass
        
        # Get unmastered vocabulary (if helpers available)
        unmastered = []
        try:
            unmastered = self.memory.semantic.helpers.get_unmastered_vocabulary(limit=10)
        except:
            pass
        
        # Build planning prompt
        planning_prompt = self._build_planning_prompt(
            duration_minutes=duration_minutes,
            past_sessions=past_sessions,
            unmastered=unmastered,
        )
        
        # Generate plan - try structured output first, fallback to text
        if hasattr(planner, 'generate_structured'):
            try:
                plan = planner.generate_structured(
                    prompt=planning_prompt,
                    response_model=SessionPlan,
                    system_prompt=self.profile.system_prompt,
                )
                plan_dict = plan.dict()
            except Exception as e:
                print(f"⚠️  Structured generation failed: {e}")
                # Fallback to text generation
                plan_text = planner.generate(
                    prompt=planning_prompt,
                    system_prompt=self.profile.system_prompt,
                    max_tokens=1000,
                )
                plan_dict = {"text": plan_text}
        else:
            # Engine doesn't support structured output - use text generation
            plan_text = planner.generate(
                prompt=planning_prompt,
                system_prompt=self.profile.system_prompt,
                max_tokens=1000,
            )
            plan_dict = {"text": plan_text}
        
        # Unload planner
        self.engines.unload_planner()
        
        # Store plan
        self.current_plan = plan_dict
        self.state = SessionState.WARMUP
        
        print("✓ Plan ready!")
        
        # Get greeting from profile
        greeting = self.profile.greeting
        
        return {
            "plan": plan_dict,
            "greeting": greeting,
            "session_id": self.session_id,
        }
    
    async def handle_text(self, user_input: str) -> TutorResponse:
        """Handle text message from user."""
        
        self.exchange_count += 1
        self.state = SessionState.CONVERSATION
        
        # Add to working memory
        self.memory.working.add_turn("user", user_input)
        
        # Get context
        try:
            context = self.memory.get_context(
                query=user_input,
                token_budget=self.memory.token_budget,
            )
        except:
            context = {}
        
        # Build prompt
        conversation_prompt = self._build_conversation_prompt(
            user_input=user_input,
            context=context,
            plan=self.current_plan,
        )
        
        # Generate response with executor (synchronous)
        response_text = self.executor.generate(
            prompt=conversation_prompt,
            system_prompt=self.profile.system_prompt,
            max_tokens=300,
        )
        
        # Add to working memory
        self.memory.working.add_turn("assistant", response_text)
        
        # Store episode (surprise-gated)
        try:
            self.memory.store_episode(
                content=f"User: {user_input}\nAssistant: {response_text}",
                metadata={
                    "type": "conversation",
                    "language": self.language,
                    "session_id": self.session_id,
                },
            )
        except Exception as e:
            print(f"⚠️  Failed to store episode: {e}")
        
        # Extract corrections and vocabulary
        corrections = self._extract_corrections(user_input, response_text)
        new_vocab = self._extract_new_vocabulary(response_text)
        
        return TutorResponse(
            text=response_text,
            corrections=corrections,
            new_vocabulary=new_vocab,
            metadata={
                "state": self.state.value,
                "tokens_used": len(response_text.split()),
            }
        )
    
    async def end_session(self) -> Dict[str, Any]:
        """End session with summary generation."""
        
        self.state = SessionState.SUMMARIZING
        duration = (time.time() - self.start_time) / 60
        
        print(f"\n📊 Generating session summary ({duration:.1f} minutes)...")
        
        # Get planner
        planner = self.engines.get_planner()
        
        # Get all conversation turns
        turns = []
        try:
            turns = self.memory.working.get_all_turns()
        except:
            pass
        
        # Build summary prompt
        summary_prompt = self._build_summary_prompt(
            plan=self.current_plan,
            turns=turns,
        )
        
        # Generate summary (synchronous)
        summary = planner.generate(
            prompt=summary_prompt,
            system_prompt="You are summarizing a language learning session.",
            max_tokens=500,
        )
        
        # Store summary
        try:
            self.memory.store_episode(
                content=summary,
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
        
        # Unload planner
        self.engines.unload_planner()
        
        # Calculate statistics
        stats = {
            "total_turns": len(turns),
            "session_duration": f"{duration:.1f} minutes",
            "exchanges": self.exchange_count,
            "corrections_made": 0,
            "new_vocabulary": 0,
        }
        
        self.state = SessionState.COMPLETED
        
        print(f"✓ Session summary generated")
        
        return {
            "summary": summary,
            "statistics": stats,
        }
    
    def _build_planning_prompt(
        self,
        duration_minutes: int,
        past_sessions: list,
        unmastered: list,
    ) -> str:
        """Build prompt for session planning."""
        
        prompt = f"""Plan a {duration_minutes}-minute {self.profile.name} tutoring session.

Student context:
"""
        
        if past_sessions:
            prompt += "\nPrevious sessions:\n"
            for session in past_sessions[:3]:
                content = getattr(session, 'content', str(session))
                prompt += f"- {content[:200]}...\n"
        
        if unmastered:
            prompt += "\nWords to practice:\n"
            for word in unmastered[:10]:
                prompt += f"- {word}\n"
        
        prompt += """
Create a balanced lesson plan with:
1. Warmup topic (conversational)
2. 2-3 focus areas (grammar/vocabulary)
3. Drill type (vocabulary, conjugation, or translation)
4. New content to introduce
5. Time allocation

Format as JSON matching the SessionPlan schema.
"""
        
        return prompt
    
    def _build_conversation_prompt(
        self,
        user_input: str,
        context: dict,
        plan: Optional[Dict],
    ) -> str:
        """Build prompt for conversation response."""
        
        prompt = ""
        
        # Add plan context
        if plan and isinstance(plan, dict):
            focus = plan.get('focus_areas', [])
            if focus:
                prompt += f"Session focus: {', '.join(focus)}\n\n"
        
        # Add memory context
        if context.get("working"):
            prompt += "Recent conversation:\n"
            for turn in context["working"]:
                prompt += f"{turn.get('role', 'unknown')}: {turn.get('content', '')}\n"
            prompt += "\n"
        
        if context.get("episodic"):
            prompt += "Relevant past context:\n"
            for episode in context["episodic"]:
                content = getattr(episode, 'content', str(episode))
                prompt += f"- {content[:100]}...\n"
            prompt += "\n"
        
        # Current message
        prompt += f"Student: {user_input}\n"
        prompt += "Tutor: "
        
        return prompt
    
    def _build_summary_prompt(
        self,
        plan: Optional[Dict],
        turns: list,
    ) -> str:
        """Build prompt for session summary."""
        
        prompt = f"""Summarize this {self.profile.name} tutoring session.

Planned objectives:
"""
        
        if plan and isinstance(plan, dict):
            focus = plan.get('focus_areas', [])
            if focus:
                prompt += ', '.join(focus)
            else:
                prompt += "General conversation"
        else:
            prompt += "General conversation"
        
        prompt += "\n\nConversation:\n"
        
        for turn in turns[:50]:
            role = getattr(turn, 'role', 'unknown')
            content = getattr(turn, 'content', str(turn))
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
    
    def _extract_corrections(self, user_input: str, response: str) -> List[dict]:
        """Extract corrections from response."""
        return []
    
    def _extract_new_vocabulary(self, response: str) -> List[dict]:
        """Extract new vocabulary from response."""
        return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics."""
        duration = (time.time() - self.start_time) / 60
        return {
            "session_id": self.session_id,
            "language": self.language,
            "duration_minutes": duration,
            "exchanges": self.exchange_count,
            "cost_per_session": self.strategy["cost_per_session"],
        }
    
    def close(self):
        """Release all resources."""
        self.memory.close()
        self.engines.shutdown()
        print(f"✓ Session {self.session_id} closed")

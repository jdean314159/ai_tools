"""
Engine Manager - Adaptive Local/Cloud Model Switching

Manages LLM engine lifecycle based on hardware strategy.
Handles loading, unloading, and switching between planner and executor engines.

Uses llm-engine API.

Author: Jeff
"""

import os
from typing import Optional, Dict, Any
from pathlib import Path

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

# All engine loading goes through llm_engines via LLMEnginesAdapter.
# The legacy engram.engine path was removed; LLMEngine remains as a runtime
# alias for type hints on planner_engine / executor_engine.
LLMEngine = Any


class EngineManager:
    """
    Manages planner and executor engines based on strategy.
    
    Key responsibilities:
    - Lazy load engines when needed
    - Unload planner after use to free VRAM
    - Handle graceful fallback if local engines fail
    - Provide consistent interface regardless of strategy
    """
    
    def __init__(self, strategy: Dict[str, Any]):
        """
        Initialize engine manager with strategy.
        
        Args:
            strategy: Strategy dict from hardware_strategy.py
        """
        self.strategy = strategy
        self.planner_engine: Optional[LLMEngine] = None
        self.executor_engine: Optional[LLMEngine] = None
        self._planner_loaded = False
        self._executor_loaded = False
    
    def get_planner(self) -> LLMEngine:
        """
        Get planning engine (lazy load).
        
        Planner is used for:
        - Session planning (start of session)
        - Session summaries (end of session)
        - Weekly progress reports (background)
        - Deep grammar explanations (on-demand)
        
        Returns:
            LLM engine configured for planning
        """
        if self.planner_engine is None:
            self.planner_engine = self._load_engine(
                self.strategy["planner"],
                purpose="planning"
            )
            self._planner_loaded = True
        
        return self.planner_engine
    
    def get_executor(self) -> LLMEngine:
        """
        Get execution engine (keep loaded).
        
        Executor is used for:
        - Real-time conversation
        - Drill execution
        - Immediate feedback
        
        Returns:
            LLM engine configured for execution
        """
        if self.executor_engine is None:
            self.executor_engine = self._load_engine(
                self.strategy["executor"],
                purpose="execution"
            )
            self._executor_loaded = True
        
        return self.executor_engine
    
    def get_memory_engine(self) -> Optional[LLMEngine]:
        """
        Get engine for memory's surprise filter.
        
        Returns:
            - Executor engine if it supports logprobs (local)
            - None if cloud-only (disables surprise filter)
        """
        memory_config = self.strategy.get("memory_engine")
        
        if memory_config == "executor":
            # Use executor for surprise filter
            executor = self.get_executor()
            
            # Verify it supports logprobs
            if hasattr(executor, 'generate_with_logprobs'):
                return executor
            else:
                print("⚠️  Executor doesn't support logprobs - surprise filter disabled")
                return None
        
        elif memory_config is None:
            # Explicitly disabled (cloud mode)
            return None
        
        else:
            raise ValueError(f"Unknown memory_engine config: {memory_config}")
    
    def unload_planner(self):
        """
        Unload planner to free VRAM.

        Sends an explicit unload request to the Ollama server so the model
        is evicted from VRAM, not just dereferenced on the Python side.

        Call this after:
        - Session planning complete
        - Session summary generated
        - Deep explanation delivered
        """
        if self.planner_engine is None:
            return

        # Tell Ollama to evict the model from VRAM immediately
        planner_model = self.strategy.get("planner", {}).get("model")
        if planner_model and self.strategy.get("planner", {}).get("engine") == "ollama":
            try:
                import urllib.request, json as _json
                base = "http://localhost:11434"
                payload = _json.dumps({
                    "model": planner_model,
                    "keep_alive": 0,           # unload immediately
                }).encode()
                req = urllib.request.Request(
                    f"{base}/api/generate",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10):
                    pass
                print(f"✓ Planner {planner_model} unloaded from Ollama VRAM")
            except Exception as e:
                print(f"⚠️  Could not signal Ollama to unload planner: {e}")

        print("🔄 Unloading planner engine object...")
        del self.planner_engine
        self.planner_engine = None
        self._planner_loaded = False

        # Clear CUDA cache if available
        if TORCH_AVAILABLE and torch.cuda.is_available():
            torch.cuda.empty_cache()

        print("✓ Planner unloaded")
    
    def _load_engine(self, config: Dict[str, Any], purpose: str):
        """
        Load an engine based on configuration via llm_engines.

        All engine loading is delegated to LLMEnginesAdapter.build_engine().
        The legacy engram.engine path was removed; setting USE_LEGACY_ENGINE=1
        now produces a clear deprecation error rather than silently falling
        back. LANGUAGE_TUTOR_ALLOW_LEGACY_ENGINE_FALLBACK is no longer read.

        Args:
            config: Engine config dict (planner or executor)
            purpose: "planning" or "execution" (for logging)

        Returns:
            LLMEnginesAdapter instance

        Raises:
            RuntimeError: If engine cannot be loaded
        """
        if os.getenv("USE_LEGACY_ENGINE", "0") == "1":
            raise RuntimeError(
                "USE_LEGACY_ENGINE is no longer supported. The engram.engine "
                "fallback was removed; all engine loading now goes through "
                "llm_engines. Unset USE_LEGACY_ENGINE."
            )

        engine_type = config.get("engine", "")
        model_name = config.get("model", "")

        try:
            from language_tutor.llm_engines_adapter import build_engine
            engine = build_engine(config)
            print(f"✓ {purpose} engine loaded via llm_engines "
                  f"({engine_type} - {model_name})")
            return engine

        except Exception as e:
            print(f"❌ Failed to load {purpose} engine: {e}")

            if engine_type in ("vllm", "ollama"):
                print("\n💡 Fallback options:")
                print("   1. Check if server is running:")
                if engine_type == "vllm":
                    print("      vllm serve <model> --port 8000")
                else:
                    print("      ollama serve")
                print("   2. Use a Gemini strategy (set GOOGLE_API_KEY)")
            elif engine_type == "anthropic":
                print("   Set ANTHROPIC_API_KEY — https://console.anthropic.com/")
            elif engine_type == "gemini":
                print("   Set GOOGLE_API_KEY — free key at https://aistudio.google.com/apikey")
            elif engine_type == "openai":
                print("   Set OPENAI_API_KEY — https://platform.openai.com/api-keys")
            elif engine_type == "llama_cpp":
                print("   Start llama-server first:")
                gguf = config.get("gguf_path") or os.getenv("LLAMA_MODEL_PATH", "<model.gguf>")
                layers = config.get("n_gpu_layers", 0)
                print(f"   llama-server -m {gguf} --n-gpu-layers {layers} --port 8080")

            raise RuntimeError(f"Cannot initialize {purpose} engine") from e

    def get_info(self) -> Dict[str, Any]:
        """Get engine status information."""
        
        return {
            "strategy": self.strategy["name"],
            "planner_loaded": self._planner_loaded,
            "executor_loaded": self._executor_loaded,
            "planner_type": self.strategy["planner"]["engine"] if self._planner_loaded else None,
            "executor_type": self.strategy["executor"]["engine"] if self._executor_loaded else None,
            "surprise_filter_enabled": self.strategy["surprise_filter"],
            "voice_enabled": self.strategy["voice_stt"]["enabled"],
            "cost_per_session": self.strategy["cost_per_session"],
        }
    
    def shutdown(self):
        """Release all engines."""
        
        if self.planner_engine:
            del self.planner_engine
            self.planner_engine = None
        
        if self.executor_engine:
            del self.executor_engine
            self.executor_engine = None
        
        if TORCH_AVAILABLE and torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        print("✓ All engines released")


class CostTracker:
    """
    Track API usage and warn about costs.
    
    Only relevant for cloud strategies. Local-only = zero cost.
    """
    
    def __init__(self, strategy: Dict[str, Any], save_path: Optional[Path] = None):
        """
        Initialize cost tracker.
        
        Args:
            strategy: Strategy dict with cost_per_session
            save_path: Path to save cost history (optional)
        """
        self.strategy = strategy
        self.save_path = save_path or Path.home() / ".language_tutor_costs.json"
        
        self.session_count = 0
        self.estimated_cost = 0.0
        
        # Load existing history if available
        self._load_history()
    
    def track_session(self):
        """Record a completed session."""
        
        self.session_count += 1
        self.estimated_cost += self.strategy["cost_per_session"]
        
        # Save history
        self._save_history()
        
        # Show summary at milestones
        if self.session_count in [5, 10, 20, 50, 100]:
            self.show_summary()
    
    def show_summary(self):
        """Display cost summary with recommendations."""
        
        cost_per = self.strategy["cost_per_session"]
        
        if cost_per == 0:
            # Local only - no costs
            print(f"\n💰 Cost Summary (Session #{self.session_count}):")
            print(f"   Total cost: $0 (local only)")
            print(f"   You've saved ~${self.session_count * 0.36:.2f} vs cloud-only!")
            return
        
        print(f"\n💰 Cost Summary (Session #{self.session_count}):")
        print(f"   Sessions: {self.session_count}")
        print(f"   Total spent: ${self.estimated_cost:.2f}")
        print(f"   Average: ${cost_per:.2f}/session")
        
        # Monthly/yearly projections
        monthly_cost = cost_per * 20  # 20 sessions/month
        yearly_cost = cost_per * 240  # 240 sessions/year
        
        print(f"\n   Projected:")
        print(f"   • Monthly (20 sessions): ${monthly_cost:.2f}")
        print(f"   • Yearly (240 sessions): ${yearly_cost:.2f}")
        
        # Hardware upgrade ROI if cloud-based
        if self.strategy["name"] in ["cloud_everything", "cloud_executor_only"]:
            self._show_hardware_roi(cost_per, yearly_cost)
    
    def _show_hardware_roi(self, cost_per: float, yearly_cost: float):
        """Show return on investment for hardware upgrades."""
        
        print(f"\n   💡 Hardware Upgrade Analysis:")
        
        # RTX 3060 12GB upgrade
        if cost_per > 0.06:
            gpu_cost = 200
            new_cost_per = 0.06
            savings_per_session = cost_per - new_cost_per
            sessions_to_break_even = gpu_cost / savings_per_session
            
            print(f"\n   Used RTX 3060 12GB (~$200):")
            print(f"   • Reduces cost to $0.06/session")
            print(f"   • Saves ${savings_per_session:.2f}/session")
            print(f"   • Breaks even after {int(sessions_to_break_even)} sessions")
            print(f"   • Enables voice features")
        
        # RTX 3090 24GB upgrade
        if cost_per > 0:
            gpu_cost = 600
            new_cost_per = 0.0
            savings_per_year = yearly_cost
            years_to_break_even = gpu_cost / savings_per_year
            
            print(f"\n   Used RTX 3090 24GB (~$600):")
            print(f"   • Reduces cost to $0/session")
            print(f"   • Saves ${yearly_cost:.2f}/year")
            print(f"   • Breaks even after {years_to_break_even:.1f} years")
            print(f"   • Full local control, maximum privacy")
    
    def _load_history(self):
        """Load cost history from disk."""
        
        if not self.save_path.exists():
            return
        
        try:
            import json
            data = json.loads(self.save_path.read_text())
            self.session_count = data.get("session_count", 0)
            self.estimated_cost = data.get("estimated_cost", 0.0)
        except Exception as e:
            print(f"⚠️  Failed to load cost history: {e}")
    
    def _save_history(self):
        """Save cost history to disk."""
        
        try:
            import json
            from datetime import datetime
            
            data = {
                "session_count": self.session_count,
                "estimated_cost": self.estimated_cost,
                "cost_per_session": self.strategy["cost_per_session"],
                "strategy": self.strategy["name"],
                "last_updated": datetime.now().isoformat(),
            }
            
            self.save_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            print(f"⚠️  Failed to save cost history: {e}")


if __name__ == "__main__":
    # Test engine manager
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    from hardware_strategy import detect_hardware, get_strategy
    
    print("Testing Engine Manager...")
    
    # Detect hardware and get strategy
    hardware = detect_hardware()
    strategy = get_strategy(hardware)
    
    if strategy is None:
        print("Cannot test - no valid strategy")
        sys.exit(1)
    
    # Create engine manager
    print(f"\nInitializing with strategy: {strategy['name']}")
    manager = EngineManager(strategy)
    
    # Test executor (keep loaded)
    print("\n--- Testing Executor ---")
    executor = manager.get_executor()
    print(f"Executor type: {type(executor).__name__}")
    
    # Test basic generation
    response = executor.generate("Say 'Hello' in one word", max_tokens=10)
    print(f"Test response: {response}")
    
    # Test memory engine
    print("\n--- Testing Memory Engine ---")
    memory_engine = manager.get_memory_engine()
    if memory_engine:
        print(f"Memory engine: {type(memory_engine).__name__}")
        print("Surprise filter: ENABLED")
    else:
        print("Memory engine: None")
        print("Surprise filter: DISABLED (cloud mode)")
    
    # Test planner (lazy load)
    print("\n--- Testing Planner ---")
    planner = manager.get_planner()
    print(f"Planner type: {type(planner).__name__}")
    
    # Unload planner
    manager.unload_planner()
    
    # Show info
    print("\n--- Engine Info ---")
    info = manager.get_info()
    for key, value in info.items():
        print(f"{key}: {value}")
    
    # Cleanup
    manager.shutdown()
    print("\n✓ Test complete")

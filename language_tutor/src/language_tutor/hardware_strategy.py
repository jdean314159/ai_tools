"""
Hardware Detection and Strategy Selection

Detects hardware capabilities and selects optimal LLM strategy.
Hardware/engine discovery delegated to engram.engine.discovery.

Author: Jeff
"""

import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Delegate hardware/engine discovery to llm_engines
from llm_engines.discovery import (
    HardwareProfile,
    OllamaModelInfo,
    EngineAvailability,
    detect_hardware,
    check_ollama_running,
    list_ollama_models,
    pull_ollama_model,
    start_ollama,
    check_disk_space,
    check_api_key,
    available_engines,
)


# Strategy definitions
STRATEGIES: Dict[str, Dict[str, Any]] = {
    "local_everything": {
        "name": "local_everything",
        "display_name": "Local Everything (Best Performance)",
        "planner": {
            "engine": "ollama",
            "model": "qwen3.6:35b-a3b",
            "num_gpu": None,   # 35B-A3B (3B active) Q4_K_M fits on RTX 3090 24GB
        },
        "executor": {
            "engine": "ollama",
            "model": "qwen3:8b",
            "num_gpu": None,   # 8B fits entirely on GPU
        },
        "memory_engine": "executor",  # Use executor for surprise filter
        "surprise_filter": True,
        "voice_stt": {
            "enabled": True,
            "model": "small",  # faster-whisper model size
        },
        "voice_tts": {
            "enabled": True,
        },
        "cost_per_session": 0.0,
        "latency": "excellent",
        "description": "Run everything locally on GPU. Zero ongoing cost, best latency.",
        "requirements": "20GB+ VRAM (RTX 3090, 4090, A6000)",
    },
    
    "hybrid_cloud_planning": {
        "name": "hybrid_cloud_planning",
        "display_name": "Hybrid (Recommended Balance)",
        "planner": {
            "engine": "anthropic",
            "model": "claude-sonnet-4-6",
        },
        "executor": {
            "engine": "vllm",
            "model": "qwen-7b-awq",
        },
        "memory_engine": "executor",  # Local executor has logprobs
        "surprise_filter": True,
        "voice_stt": {
            "enabled": True,
            "model": "small",
        },
        "voice_tts": {
            "enabled": True,
        },
        "cost_per_session": 0.06,
        "latency": "good",
        "description": "Cloud for planning/summaries, local for conversation. Best cost/quality balance.",
        "requirements": "10GB+ VRAM (RTX 3060 12GB, 4060 Ti) + Anthropic API key",
        "cost_breakdown": {
            "planning": 0.03,
            "summary": 0.03,
            "conversation": 0.0,
        },
    },
    
    "cloud_executor_only": {
        "name": "cloud_executor_only",
        "display_name": "Cloud Budget Mode",
        "planner": {
            "engine": "anthropic",
            "model": "claude-sonnet-4-6",
        },
        "executor": {
            "engine": "anthropic",
            "model": "claude-haiku-4-5-20251001",  # Cheaper model
        },
        "memory_engine": None,  # No logprobs in cloud mode
        "surprise_filter": False,
        "voice_stt": {
            "enabled": False,  # Too slow with cloud executor
        },
        "voice_tts": {
            "enabled": False,
        },
        "cost_per_session": 0.15,
        "latency": "good",
        "description": "Text-only, cloud-based. Sonnet for planning, Haiku for conversation. Budget option.",
        "requirements": "Anthropic API key only",
        "cost_breakdown": {
            "planning": 0.03,
            "summary": 0.03,
            "conversation": 0.09,
        },
    },
    
    "cloud_everything": {
        "name": "cloud_everything",
        "display_name": "Cloud Premium Mode",
        "planner": {
            "engine": "anthropic",
            "model": "claude-sonnet-4-6",
        },
        "executor": {
            "engine": "anthropic",
            "model": "claude-sonnet-4-6",
        },
        "memory_engine": None,
        "surprise_filter": False,
        "voice_stt": {"enabled": False},
        "voice_tts": {"enabled": False},
        "cost_per_session": 0.36,
        "latency": "acceptable",
        "description": "Text-only, cloud-based. Highest quality responses, higher cost.",
        "requirements": "Anthropic API key only",
        "cost_breakdown": {"planning": 0.03, "summary": 0.03, "conversation": 0.30},
    },

    # ── Gemini strategies ──────────────────────────────────────────────

    "gemini_planning": {
        "name": "gemini_planning",
        "display_name": "Gemini Planning + Local 9B",
        "planner": {
            "engine": "gemini",
            "model":  "gemini-2.0-flash",
        },
        "executor": {
            "engine":   "ollama",
            "model":    "qwen3:8b",
            "num_gpu":  None,
        },
        "memory_engine": None,
        "surprise_filter": False,
        "voice_stt": {"enabled": True},
        "voice_tts": {"enabled": True},
        "cost_per_session": 0.0,   # Gemini free tier
        "latency": "good",
        "description": (
            "Gemini Flash for planning/explanations (fast, free), "
            "local qwen3:8b for conversation (private). "
            "Best for workstation — fast planning, private conversation."
        ),
        "requirements": "GOOGLE_API_KEY + Ollama with qwen3:8b",
    },

    "gemini_local_3b": {
        "name": "gemini_local_3b",
        "display_name": "Gemini Planning + Local 8B (laptop)",
        "planner": {
            "engine": "gemini",
            "model":  "gemini-2.0-flash",
        },
        "executor": {
            "engine":  "ollama",
            "model":   "qwen3:8b",
            "num_gpu": None,   # Ollama auto-allocates; fits mostly on GTX 1650 4GB
        },
        "memory_engine": None,
        "surprise_filter": False,
        "voice_stt": {"enabled": True},
        "voice_tts": {"enabled": True},
        "cost_per_session": 0.0,
        "latency": "good",
        "description": (
            "Gemini Flash for planning/explanations, "
            "local 3B model via llama.cpp for conversation. "
            "Ideal for GTX 1650 laptop — all conversation stays private."
        ),
        "requirements": "GOOGLE_API_KEY + llama-server with qwen3.2-3b GGUF",
    },

    "gemini_everything": {
        "name": "gemini_everything",
        "display_name": "Gemini Only (no local models)",
        "planner": {
            "engine": "gemini",
            "model":  "gemini-2.0-flash",
        },
        "executor": {
            "engine": "gemini",
            "model":  "gemini-2.0-flash",
        },
        "memory_engine": None,
        "surprise_filter": False,
        "voice_stt": {"enabled": False},
        "voice_tts": {"enabled": False},
        "cost_per_session": 0.0,
        "latency": "good",
        "description": (
            "All LLM calls via Gemini Flash free tier. "
            "No local models, no GPU required. "
            "Ideal for travel or any machine without Ollama."
        ),
        "requirements": "GOOGLE_API_KEY only",
    },

    # ── OpenAI strategies ──────────────────────────────────────────────

    "openai_planning": {
        "name": "openai_planning",
        "display_name": "OpenAI Planning + Local 9B",
        "planner": {
            "engine": "openai",
            "model":  "gpt-4o-mini",
        },
        "executor": {
            "engine":  "ollama",
            "model":   "qwen3:8b",
            "num_gpu": None,
        },
        "memory_engine": None,
        "surprise_filter": False,
        "voice_stt": {"enabled": True},
        "voice_tts": {"enabled": True},
        "cost_per_session": 0.01,
        "latency": "good",
        "description": (
            "GPT-4o-mini for planning/explanations, "
            "local qwen3:8b for conversation (private). "
            "Good workstation option if you have an OpenAI key."
        ),
        "requirements": "OPENAI_API_KEY + Ollama with qwen3:8b",
    },

    "openai_local_3b": {
        "name": "openai_local_3b",
        "display_name": "OpenAI Planning + Local 8B (laptop)",
        "planner": {
            "engine": "openai",
            "model":  "gpt-4o-mini",
        },
        "executor": {
            "engine":  "ollama",
            "model":   "qwen3:8b",
            "num_gpu": None,
        },
        "memory_engine": None,
        "surprise_filter": False,
        "voice_stt": {"enabled": True},
        "voice_tts": {"enabled": True},
        "cost_per_session": 0.01,
        "latency": "good",
        "description": (
            "GPT-4o-mini for planning/explanations, "
            "local qwen3:8b for conversation. "
            "Laptop option with OpenAI key."
        ),
        "requirements": "OPENAI_API_KEY + Ollama with qwen3:8b",
    },

    "openai_everything": {
        "name": "openai_everything",
        "display_name": "OpenAI Only (no local models)",
        "planner": {
            "engine": "openai",
            "model":  "gpt-4o-mini",
        },
        "executor": {
            "engine": "openai",
            "model":  "gpt-4o-mini",
        },
        "memory_engine": None,
        "surprise_filter": False,
        "voice_stt": {"enabled": False},
        "voice_tts": {"enabled": False},
        "cost_per_session": 0.01,
        "latency": "good",
        "description": (
            "All LLM calls via GPT-4o-mini. "
            "No local models or GPU required. "
            "~$0.01/session via OpenAI API."
        ),
        "requirements": "OPENAI_API_KEY only",
    },
}



def get_strategy(
    hardware: Optional[HardwareProfile] = None,
    override: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Select optimal strategy based on hardware and preferences.
    
    Args:
        hardware: Detected hardware profile. If None, auto-detect.
        override: Manual override strategy name from env var
    
    Returns:
        Strategy dict, or None if configuration impossible
    """
    # Check for manual override
    if override:
        if override in STRATEGIES:
            print(f"ℹ️  Using manual override: {override}")
            return STRATEGIES[override]
        else:
            print(f"⚠️  Unknown strategy '{override}', using auto-detect")
    
    # Auto-detect hardware if not provided
    if hardware is None:
        hardware = detect_hardware()
    
    # Check API key availability
    has_api_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    
    # Get recommended strategy
    strategy_name = hardware.recommended_strategy
    
    # Validate strategy is possible
    strategy = STRATEGIES[strategy_name]
    
    # Check if strategy requires API key
    needs_api = strategy["planner"]["engine"] == "anthropic" or \
                strategy["executor"]["engine"] == "anthropic"
    
    if needs_api and not has_api_key:
        print("\n❌ Selected strategy requires Anthropic API key")
        print("   Get one at: https://console.anthropic.com/")
        print("   Then: export ANTHROPIC_API_KEY='your-key-here'")
        
        # Check if local-only possible
        if hardware.can_run_7b:
            print("\n   💡 You have GPU - consider installing Ollama for local 32B:")
            print("      https://ollama.ai/")
            return None
        else:
            print("\n   No local GPU available. API key required.")
            return None
    
    return strategy


def show_strategy_info(strategy: Dict[str, Any], hardware: HardwareProfile):
    """Display strategy information and costs."""
    
    print("\n" + "=" * 60)
    print(f"Selected Strategy: {strategy['display_name']}")
    print("=" * 60)
    
    print(f"\nDescription: {strategy['description']}")
    print(f"Requirements: {strategy['requirements']}")
    
    print(f"\n📊 Configuration:")
    print(f"   Planner: {strategy['planner']['engine']} - {strategy['planner']['model']}")
    print(f"   Executor: {strategy['executor']['engine']} - {strategy['executor']['model']}")
    print(f"   Surprise Filter: {'✓ Enabled' if strategy['surprise_filter'] else '✗ Disabled'}")
    print(f"   Voice: {'✓ Enabled' if strategy['voice_stt']['enabled'] else '✗ Disabled'}")
    
    print(f"\n💰 Cost per session: ${strategy['cost_per_session']:.2f}")
    
    if strategy['cost_per_session'] > 0:
        print(f"   Monthly (20 sessions): ${strategy['cost_per_session'] * 20:.2f}")
        print(f"   Yearly (240 sessions): ${strategy['cost_per_session'] * 240:.2f}")
        
        if 'cost_breakdown' in strategy:
            print(f"\n   Breakdown:")
            for item, cost in strategy['cost_breakdown'].items():
                print(f"      {item.capitalize()}: ${cost:.2f}")
        
        # Show hardware upgrade ROI if applicable
        if not hardware.can_run_7b and strategy['cost_per_session'] > 0.06:
            sessions_to_break_even_3060 = 200 / (strategy['cost_per_session'] - 0.06)
            print(f"\n   💡 Hardware Upgrade Option:")
            print(f"      Used RTX 3060 12GB: ~$200")
            print(f"      → Reduces cost to $0.06/session")
            print(f"      → Breaks even after {int(sessions_to_break_even_3060)} sessions")
    else:
        print("   Free! (local only)")
    
    print(f"\n⚡ Latency: {strategy['latency']}")
    print("=" * 60)


def save_config(strategy: Dict[str, Any], hardware: HardwareProfile, path: Path):
    """Save configuration to JSON file."""
    
    config = {
        "strategy": strategy["name"],
        "hardware": hardware.to_dict(),
        "created": datetime.now().isoformat(),
        "full_strategy": strategy,
    }
    
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2))
    print(f"\n✓ Configuration saved to {path}")


def load_config(path: Path) -> Optional[Dict[str, Any]]:
    """Load configuration from JSON file."""
    
    if not path.exists():
        return None
    
    try:
        config = json.loads(path.read_text())
        return config
    except Exception as e:
        print(f"⚠️  Failed to load config: {e}")
        return None


def setup_wizard() -> Optional[Dict[str, Any]]:
    """Interactive setup wizard — detects hardware, shows viable strategies,
    validates model availability, and offers to download missing models.

    Returns selected strategy dict, or None if setup cancelled.
    """
    print("\n🎓 Language Tutor Setup Wizard")
    print("=" * 60)

    # ── 1. Detect hardware and engine availability ──────────────────
    print("\n🔍 Detecting hardware and available engines…")
    hw      = detect_hardware()
    avail   = available_engines()

    gpu_str = f"{hw.gpu_name} ({hw.vram_gb:.1f}GB VRAM)" if hw.gpu_name else "No GPU detected"
    print(f"  GPU    : {gpu_str}")
    print(f"  RAM    : {hw.ram_gb:.0f}GB")
    print(f"  Ollama : {'✓ running' if avail.ollama_running else '✗ not running'}")
    if avail.ollama_models:
        print(f"  Models : {', '.join(m.name for m in avail.ollama_models[:5])}")
    print(f"  GOOGLE_API_KEY    : {'✓' if avail.has_google_key else '✗ not set'}")
    print(f"  ANTHROPIC_API_KEY : {'✓' if avail.has_anthropic_key else '✗ not set'}")
    print(f"  OPENAI_API_KEY    : {'✓' if avail.has_openai_key else '✗ not set'}")

    # ── 2. Score and filter strategies ──────────────────────────────
    viable   = []
    marginal = []   # viable after downloading a model
    blocked  = []

    # Model size hints for download prompt
    MODEL_SIZES = {
        # Qwen3.6 (latest, May 2026): multimodal, 256K context
        "qwen3.6:35b-a3b": 24.0, "qwen3.6:27b":    17.0,
        # Qwen3 family (April 2026): broad dense + MoE coverage
        "qwen3:8b":         5.2, "qwen3:14b":       9.3, "qwen3:32b": 20.0,
        "qwen3:30b-a3b":   17.0,
        # Qwen3.5 retained for older configs and fallback
        "qwen3.5:27b":     17.0, "qwen3.5:9b":      6.6,
        # Qwen2.5 retained for low-VRAM fallback
        "qwen2.5:7b":       4.7, "qwen2.5:32b":    19.0,
    }

    for name, s in STRATEGIES.items():
        reasons_blocked  = []
        reasons_marginal = []

        for role in ("planner", "executor"):
            cfg    = s.get(role, {})
            engine = cfg.get("engine", "")
            model  = cfg.get("model", "")

            if engine == "ollama":
                if not avail.ollama_running:
                    reasons_blocked.append("Ollama not running")
                elif not avail.has_model(model):
                    size = MODEL_SIZES.get(model, 0)
                    reasons_marginal.append((model, size))
            elif engine in ("gemini", "google"):
                if not avail.has_google_key:
                    reasons_blocked.append("GOOGLE_API_KEY not set")
            elif engine == "anthropic":
                if not avail.has_anthropic_key:
                    reasons_blocked.append("ANTHROPIC_API_KEY not set")
            elif engine == "openai":
                if not avail.has_openai_key:
                    reasons_blocked.append("OPENAI_API_KEY not set")

        if reasons_blocked:
            blocked.append((name, s, list(set(reasons_blocked))))
        elif reasons_marginal:
            marginal.append((name, s, reasons_marginal))
        else:
            viable.append((name, s))

    # ── 3. Determine recommendation ─────────────────────────────────
    PRIORITY = [
        "local_everything", "gemini_planning", "openai_planning",
        "gemini_local_3b", "openai_local_3b",
        "gemini_everything", "openai_everything",
        "hybrid_cloud_planning", "cloud_executor_only", "cloud_everything",
    ]

    recommended_name = None
    if viable:
        for p in PRIORITY:
            if any(n == p for n, _ in viable):
                recommended_name = p
                break
        if not recommended_name:
            recommended_name = viable[0][0]
    elif marginal:
        recommended_name = marginal[0][0]

    # ── 4. Display options ───────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Available strategies:")
    print("=" * 60)

    all_choices = []

    def _show_group(group, label):
        if not group:
            return
        print(f"\n  {label}")
        for item in group:
            if len(item) == 2:
                name, s = item; note = ""
            else:
                name, s, info = item
                if isinstance(info[0], tuple):
                    note = f"  [needs: {', '.join(f'{m}({sz:.0f}GB)' for m,sz in info)}]"
                else:
                    note = f"  [blocked: {', '.join(info)}]"
            idx = len(all_choices) + 1
            rec = " ← recommended" if name == recommended_name else ""
            all_choices.append(name)
            cost = s['cost_per_session']
            cost_str = "free" if cost == 0 else f"${cost:.2f}/session"
            print(f"  {idx:2d}. {s['display_name']:<40} {cost_str}{rec}{note}")

    _show_group(viable,   "✓ Ready to use:")
    _show_group(marginal, "⬇  Available (model download required):")
    _show_group(blocked,  "✗ Not available (missing API key or Ollama):")

    if not all_choices:
        print("\n❌ No strategies available. Check that Ollama is running or an API key is set.")
        return None

    # ── 5. User picks ────────────────────────────────────────────────
    print()
    default = all_choices.index(recommended_name) + 1 if recommended_name in all_choices else 1
    try:
        raw = input(f"Select strategy [1-{len(all_choices)}, default={default}]: ").strip()
        choice = int(raw) if raw else default
        if not 1 <= choice <= len(all_choices):
            raise ValueError()
    except (ValueError, EOFError):
        print("Invalid choice. Using recommendation.")
        choice = default

    selected_name = all_choices[choice - 1]
    selected      = STRATEGIES[selected_name]

    print(f"\n✓ Selected: {selected['display_name']}")
    print(f"  {selected['description']}")

    # ── 6. Validate / offer to download missing models ───────────────
    for role in ("planner", "executor"):
        cfg    = selected.get(role, {})
        engine = cfg.get("engine", "")
        model  = cfg.get("model", "")
        if engine != "ollama" or not model:
            continue
        if avail.has_model(model):
            print(f"  {role.capitalize()} model {model}: ✓ present")
            continue

        # Model missing
        if not avail.ollama_running:
            print(f"\n  Ollama is not running. Attempting to start…")
            if start_ollama():
                print("  ✓ Ollama started")
                avail = available_engines()
            else:
                print("  ✗ Could not start Ollama. Start it manually: ollama serve")
                return None

        size_hint = MODEL_SIZES.get(model, 0)
        size_str  = f" ({size_hint:.0f}GB)" if size_hint else ""
        ok_disk, free_gb = check_disk_space("/", required_gb=size_hint * 1.1)
        if not ok_disk:
            print(f"  ⚠️  Only {free_gb:.1f}GB free — {model} needs ~{size_hint:.0f}GB. Free up space first.")
            return None

        try:
            ans = input(f"\n  {role.capitalize()} model {model}{size_str} not found. Download now? [y/n]: ").strip().lower()
        except EOFError:
            ans = "n"

        if ans == "y":
            print(f"  Pulling {model}… (Ctrl+C to cancel)")
            last_pct = [0]

            def _progress(pct, dl, total):
                p = int(pct)
                if p - last_pct[0] >= 5:
                    bar = "█" * (p // 5) + "░" * (20 - p // 5)
                    print(f"  [{bar}] {p:3d}%  {dl:.1f}/{total:.1f}GB", end="\r", flush=True)
                    last_pct[0] = p

            success = pull_ollama_model(model, progress_callback=_progress)
            print()
            if success:
                print(f"  ✓ {model} ready")
            else:
                print(f"  ✗ Pull failed. Run manually: ollama pull {model}")
                return None
        else:
            print(f"  Skipped. Run: ollama pull {model}")
            return None

    # ── 7. Save and return ───────────────────────────────────────────
    config_path = Path.home() / ".language_tutor_config.json"
    save_config(selected, hw, config_path)
    print("\n✓ Setup complete! Run ./start.sh to start the tutor.")
    print("  To reconfigure: ./start.sh --setup")
    return selected


if __name__ == "__main__":
    # Test hardware detection
    print("Testing hardware detection...")
    hardware = detect_hardware()
    
    print(f"\nHardware Profile:")
    print(f"  Name: {hardware.name}")
    print(f"  GPU: {hardware.gpu_name}")
    print(f"  VRAM: {hardware.vram_gb:.1f}GB")
    print(f"  Can run 7B: {hardware.can_run_7b}")
    print(f"  Can run 32B: {hardware.can_run_32b}")
    print(f"  Can run voice: {hardware.can_run_voice}")
    print(f"  Recommended: {hardware.recommended_strategy}")
    
    # Show all available strategies
    print("\n\nAvailable Strategies:")
    print("=" * 60)
    for name, strategy in STRATEGIES.items():
        print(f"\n{strategy['display_name']}")
        print(f"  {strategy['description']}")
        print(f"  Cost: ${strategy['cost_per_session']:.2f}/session")
        print(f"  Requirements: {strategy['requirements']}")

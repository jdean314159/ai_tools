"""
Language Tutor — CLI entry point

Interactive command-line session for development and testing.
For the web UI, run:  python -m language_tutor.app

Usage:
    python main_example.py           # interactive setup + session
    python main_example.py --test    # non-interactive quick test (dev only)

Author: Jeff
"""

import asyncio
import os
import sys
from pathlib import Path

# Ensure the package is importable from the project root
sys.path.insert(0, str(Path(__file__).parent))

from language_tutor.hardware_strategy import (
    detect_hardware,
    get_strategy,
    load_config,
    setup_wizard,
    STRATEGIES,
)
from language_tutor.tutor_session import TutorSession


async def run_interactive():
    """Interactive session with setup wizard on first run."""

    print("🎓 Language Tutor")
    print("=" * 60)

    config_path = Path.home() / ".language_tutor_config.json"
    config = load_config(config_path)

    if config is None:
        print("\nFirst-time setup required.\n")
        strategy = setup_wizard()
        if strategy is None:
            print("\n❌ Setup incomplete. Exiting.")
            return
    else:
        strategy_name = config.get("strategy", "")
        strategy = STRATEGIES.get(strategy_name) or config.get("full_strategy")
        print(f"\n✓ Loaded strategy: {strategy_name}")
        ans = input("Use this configuration? (y/n): ").strip().lower()
        if ans != "y":
            strategy = setup_wizard()
            if strategy is None:
                return

    print(f"\n  Strategy : {strategy['display_name']}")
    print(f"  Cost     : ${strategy['cost_per_session']:.2f}/session")
    print(f"  Voice    : {'Enabled' if strategy['voice_stt']['enabled'] else 'Disabled'}")

    print("\nSelect language:")
    print("  1. Spanish")
    print("  2. Latin")
    choice = input("Choice (1/2): ").strip()
    language = "latin" if choice == "2" else "spanish"

    base_dir = Path("data")
    base_dir.mkdir(parents=True, exist_ok=True)

    session = TutorSession(language=language, strategy=strategy, base_dir=base_dir)

    try:
        await session.start(duration_minutes=30)

        print("\n💬 Session started! Type 'quit' or 'adiós' to end.\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "adiós", "adios", "bye", "vale"):
                break

            response = await session.handle_text(user_input)
            print(f"Tutor: {response.text}\n")

            if response.corrections:
                for c in response.corrections:
                    print(f"  ✏️  {c.get('error')} → {c.get('correction')}")
                print()

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted.")
    finally:
        print("\nGenerating session summary…")
        result = await session.end_session()
        print("\n" + "=" * 60)
        print(result.get("summary", ""))
        stats = result.get("statistics", {})
        print(
            f"\nDuration: {stats.get('session_duration', '?')}  |  "
            f"Exchanges: {stats.get('exchanges', 0)}  |  "
            f"Corrections: {stats.get('corrections_made', 0)}  |  "
            f"New vocab: {stats.get('new_vocabulary', 0)}"
        )
        session.close()


async def quick_test():
    """Non-interactive smoke test for development."""

    print("🧪 Quick test mode\n")

    hardware = detect_hardware()
    override = os.getenv("LANGUAGE_TUTOR_STRATEGY")
    strategy = get_strategy(hardware, override=override)

    if strategy is None:
        print("No valid strategy — check hardware or set LANGUAGE_TUTOR_STRATEGY.")
        return

    print(f"Strategy : {strategy['name']}")

    base_dir = Path("/tmp/lt_quick_test")
    base_dir.mkdir(exist_ok=True)

    session = TutorSession(language="spanish", strategy=strategy, base_dir=base_dir)

    try:
        await session.start(duration_minutes=10)

        for msg in [
            "Hola, ¿cómo estás?",
            "Quiero practicar el pretérito irregular.",
            "Yo ser muy cansado ayer.",
        ]:
            print(f"\nYou: {msg}")
            resp = await session.handle_text(msg)
            print(f"Tutor: {resp.text[:200]}")

        result = await session.end_session()
        print(f"\nSummary: {result['summary'][:300]}")
        print(f"Stats:   {result['statistics']}")

    finally:
        session.close()
        print("\n✓ Test complete")


if __name__ == "__main__":
    if "--test" in sys.argv:
        asyncio.run(quick_test())
    else:
        asyncio.run(run_interactive())

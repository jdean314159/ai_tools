"""Interactive first-run configuration for the recovered reference app."""

import json
from datetime import datetime
from pathlib import Path

from llm_engines.discovery import detect_hardware

from language_tutor.hardware_strategy import get_strategy


def setup_wizard():
    """Interactive setup for hardware/cost preferences."""

    print("🎓 Language Tutor Setup")
    print("=" * 50)

    # Detect hardware
    hardware = detect_hardware()
    gpu = hardware.primary_gpu
    print(f"\nDetected: {gpu.name if gpu else 'No GPU'}")
    print(f"VRAM: {hardware.vram_total_mb / 1024:.1f}GB")

    # Get strategy
    strategy = get_strategy(hardware)

    if strategy is None:
        return None

    # Show cost expectations
    print(f"\n📊 Configuration: {strategy.get('note', '')}")
    print(f"   Cost per session: ${strategy['cost_per_session']:.2f}")
    print(f"   Estimated monthly (20 sessions): ${strategy['cost_per_session'] * 20:.2f}")

    if strategy["cost_per_session"] > 0:
        print("\n   💡 This adds up over time. Consider:")
        print("      • Used GPU: RTX 3060 12GB (~$200) → $0.06/session")
        print("      • Used GPU: RTX 3090 24GB (~$600) → $0.00/session")

    # Voice availability
    if strategy["voice_stt"]["enabled"]:
        print("\n🎤 Voice: Enabled")
    else:
        print("\n🔇 Voice: Disabled (requires local GPU)")

    # Confirm
    print("\n" + "=" * 50)
    response = input("Proceed with this configuration? (y/n): ")

    if response.lower() != "y":
        print("Setup cancelled.")
        return None

    # Save config
    config_path = Path("~/.language_tutor_config.json").expanduser()
    config_path.write_text(
        json.dumps(
            {
                "strategy": strategy,
                "hardware": hardware.model_dump(mode="json"),
                "created": datetime.now().isoformat(),
            },
            indent=2,
        )
    )

    print(f"\n✓ Configuration saved to {config_path}")
    return strategy

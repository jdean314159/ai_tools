# On first run, show configuration wizard

def setup_wizard():
    """Interactive setup for hardware/cost preferences."""
    
    print("🎓 Language Tutor Setup")
    print("=" * 50)
    
    # Detect hardware
    hardware = detect_hardware()
    print(f"\nDetected: {hardware.gpu_name or 'No GPU'}")
    print(f"VRAM: {hardware.vram_gb:.1f}GB")
    print(f"Recommended: {hardware.recommended_strategy}")
    
    # Check API key
    has_api_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    if not has_api_key:
        print("\n⚠️  No Anthropic API key found")
        print("   Get one at: https://console.anthropic.com/")
        print("   Then: export ANTHROPIC_API_KEY='your-key-here'")
        
        if hardware.can_run_7b or hardware.can_run_32b:
            print("\n   You can still use local models!")
        else:
            print("\n   ❌ Cannot run without API key or GPU")
            return None
    
    # Get strategy
    strategy = get_strategy(hardware, has_api_key)
    
    if strategy is None:
        return None
    
    # Show cost expectations
    print(f"\n📊 Configuration: {strategy.get('note', '')}")
    print(f"   Cost per session: ${strategy['cost_per_session']:.2f}")
    print(f"   Estimated monthly (20 sessions): ${strategy['cost_per_session'] * 20:.2f}")
    
    if strategy['cost_per_session'] > 0:
        print(f"\n   💡 This adds up over time. Consider:")
        print(f"      • Used GPU: RTX 3060 12GB (~$200) → $0.06/session")
        print(f"      • Used GPU: RTX 3090 24GB (~$600) → $0.00/session")
    
    # Voice availability
    if strategy['voice_stt']['enabled']:
        print(f"\n🎤 Voice: Enabled")
    else:
        print(f"\n🔇 Voice: Disabled (requires local GPU)")
    
    # Confirm
    print("\n" + "=" * 50)
    response = input("Proceed with this configuration? (y/n): ")
    
    if response.lower() != 'y':
        print("Setup cancelled.")
        return None
    
    # Save config
    config_path = Path("~/.language_tutor_config.json").expanduser()
    config_path.write_text(json.dumps({
        "strategy": strategy,
        "hardware": asdict(hardware),
        "created": datetime.now().isoformat(),
    }, indent=2))
    
    print(f"\n✓ Configuration saved to {config_path}")
    return strategy

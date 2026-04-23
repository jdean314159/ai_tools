#!/usr/bin/env python3
"""
Language Tutor Project Builder

Creates the complete directory structure and Phase 1 files for the language tutor.

Usage:
    python create_language_tutor_project.py [target_directory]

Default target: ~/ai-projects/language_tutor
"""

import sys
import shutil
from pathlib import Path
from datetime import datetime


def create_project_structure(base_dir: Path):
    """Create the complete directory structure."""
    
    print(f"Creating project structure in: {base_dir}")
    
    # Main directories
    dirs = [
        # Package root
        "language_tutor",
        
        # Core modules
        "language_tutor/voice",
        "language_tutor/drills",
        "language_tutor/content",
        "language_tutor/routes",
        "language_tutor/templates",
        "language_tutor/templates/components",
        "language_tutor/templates/static",
        "language_tutor/templates/static/css",
        "language_tutor/templates/static/js",
        
        # Tests
        "tests",
        "tests/integration",
        
        # Data directories
        "data/memory",
        "data/voices",
        "data/models",
    ]
    
    for dir_path in dirs:
        full_path = base_dir / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        print(f"  ✓ Created {dir_path}/")
    
    return base_dir


def copy_existing_files(base_dir: Path, source_dir: Path):
    """Copy the files we already created."""
    
    print("\nCopying existing implementation files...")
    
    files_to_copy = [
        ("hardware_strategy.py", "language_tutor/hardware_strategy.py"),
        ("engine_manager.py", "language_tutor/engine_manager.py"),
        ("tutor_session.py", "language_tutor/tutor_session.py"),
        ("main_example.py", "main_example.py"),
        ("HARDWARE_ADAPTIVE_README.md", "HARDWARE_ADAPTIVE_README.md"),
    ]
    
    for source_file, dest_file in files_to_copy:
        src = source_dir / source_file
        dst = base_dir / dest_file
        
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  ✓ Copied {source_file}")
        else:
            print(f"  ⚠ Skipped {source_file} (not found)")


def create_init_files(base_dir: Path):
    """Create __init__.py files."""
    
    print("\nCreating __init__.py files...")
    
    init_locations = [
        "language_tutor/__init__.py",
        "language_tutor/voice/__init__.py",
        "language_tutor/drills/__init__.py",
        "language_tutor/content/__init__.py",
        "language_tutor/routes/__init__.py",
        "tests/__init__.py",
        "tests/integration/__init__.py",
    ]
    
    for location in init_locations:
        init_file = base_dir / location
        init_file.write_text('"""Package initialization."""\n')
        print(f"  ✓ Created {location}")


def create_config_file(base_dir: Path):
    """Create config.py with language profiles."""
    
    content = '''"""
Language Tutor Configuration

Language profiles, settings, and constants.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class LanguageProfile:
    """Configuration for a specific language."""
    
    code: str                          # ISO code: "es", "la"
    name: str                          # Display name: "Spanish", "Latin"
    native_name: str                   # Name in that language
    
    # Engine configuration (set dynamically from strategy)
    executor_engine: str               # "vllm", "anthropic"
    executor_model: str                # Model name
    
    # Voice configuration
    supports_voice: bool               # Can use STT/TTS
    whisper_language: str              # Whisper language code
    tts_backend: str                   # "piper", "xtts"
    tts_voice: Optional[str]          # Piper voice name or None for XTTS
    voice_clone_sample: Optional[Path]  # For XTTS cloning
    
    # Pronunciation
    needs_phonetic_mapping: bool       # True for Latin
    
    # LLM prompts
    system_prompt: str
    greeting: str


def get_language_profile(language: str, strategy: dict) -> LanguageProfile:
    """
    Get language profile adapted to current hardware strategy.
    
    Args:
        language: "spanish" or "latin"
        strategy: Strategy dict from hardware_strategy.py
    
    Returns:
        LanguageProfile configured for this language + strategy
    """
    
    base_profiles = {
        "spanish": {
            "code": "es",
            "name": "Spanish",
            "native_name": "Español",
            "whisper_language": "es",
            "tts_backend": "piper",
            "tts_voice": "es_MX-claude-high",
            "voice_clone_sample": None,
            "needs_phonetic_mapping": False,
            "system_prompt": (
                "Eres un tutor profesional de español. Hablas con un estudiante "
                "anglohablante de nivel intermedio. Mezcla español e inglés según "
                "sea necesario. Corrige errores amablemente. Enfócate en la "
                "conversación natural. Si el estudiante comete un error, repite "
                "la forma correcta en contexto."
            ),
            "greeting": "¡Hola! ¿Cómo estás hoy? ¿Qué quieres practicar?",
        },
        
        "latin": {
            "code": "la",
            "name": "Latin",
            "native_name": "Latina",
            "whisper_language": "la",
            "tts_backend": "xtts",
            "tts_voice": None,
            "voice_clone_sample": Path("data/voices/wife_sample.wav"),
            "needs_phonetic_mapping": True,
            "system_prompt": (
                "You are a Classical Latin tutor. Use Classical pronunciation "
                "(not Ecclesiastical). The student is an English speaker learning "
                "Latin. Explain grammar in English. Present Latin text with "
                "macrons where appropriate. Focus on: noun declensions, verb "
                "conjugations, sentence structure (SOV), and reading comprehension."
            ),
            "greeting": "Salvē! Quid agis hodiē?",
        },
    }
    
    if language not in base_profiles:
        raise ValueError(f"Unknown language: {language}")
    
    profile_data = base_profiles[language]
    
    return LanguageProfile(
        **profile_data,
        executor_engine=strategy["executor"]["engine"],
        executor_model=strategy["executor"]["model"],
        supports_voice=strategy["voice"],
    )


# Application settings
APP_TITLE = "Language Tutor"
APP_VERSION = "0.1.0"

# Default token budgets
DEFAULT_TOKEN_BUDGET = {
    "working": 1000,
    "episodic": 800,
    "semantic": 400,
}

# Session settings
DEFAULT_SESSION_DURATION = 30  # minutes
AUTO_SAVE_INTERVAL = 300       # seconds (5 minutes)

# Voice settings
WHISPER_MODEL_SIZE = "small"   # "tiny", "base", "small", "medium"
WHISPER_DEVICE = "cuda"        # "cuda" or "cpu"

# Piper TTS settings
PIPER_TIMEOUT = 30             # seconds

# Cost tracking milestones (show summary at these session counts)
COST_MILESTONES = [5, 10, 20, 50, 100]
'''
    
    (base_dir / "language_tutor" / "config.py").write_text(content)
    print("  ✓ Created config.py")


def create_spanish_content(base_dir: Path, spanish_tutor_path: Path):
    """Copy Spanish content from spanish_tutor project."""
    
    print("\nCopying Spanish content data...")
    
    source = spanish_tutor_path / "services" / "content_data.py"
    dest = base_dir / "language_tutor" / "content" / "spanish.py"
    
    if source.exists():
        # Copy the file
        shutil.copy2(source, dest)
        
        # Add header comment
        original = dest.read_text()
        header = '''"""
Spanish Language Content Data

Vocabulary, verb conjugations, practice sentences, and drill content.
Imported from previous spanish_tutor project.
"""

'''
        dest.write_text(header + original)
        print("  ✓ Copied Spanish content data")
    else:
        # Create minimal placeholder
        content = '''"""
Spanish Language Content Data

TODO: Copy from spanish_tutor/services/content_data.py
"""

# Irregular verbs
IRREGULAR_VERBS = {
    "ser": {
        "preterite": {"yo": "fui", "tú": "fuiste", "él": "fue"},
        "imperfect": {"yo": "era", "tú": "eras", "él": "era"},
    },
}

# Practice sentences
PRACTICE_SENTENCES = [
    ("Me llamo Jeff", "My name is Jeff"),
    ("¿Cómo estás?", "How are you?"),
]
'''
        dest.write_text(content)
        print("  ⚠ Created placeholder Spanish content (copy full data later)")


def create_preflight_check(base_dir: Path):
    """Create preflight_check.py system validation."""
    
    content = '''"""
Pre-Flight System Check

Validates system configuration before starting language tutor.
"""

import sys
import os
from pathlib import Path
from typing import List, Tuple

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from language_tutor.hardware_strategy import detect_hardware, get_strategy


class LanguageTutorPreflight:
    """Pre-flight system validation."""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def run_all_checks(self) -> bool:
        """
        Run all pre-flight checks.
        
        Returns:
            True if all critical checks pass
        """
        print("\\n" + "=" * 70)
        print("LANGUAGE TUTOR PRE-FLIGHT CHECK")
        print("=" * 70 + "\\n")
        
        checks = [
            ("Hardware Detection", self.check_hardware),
            ("Strategy Selection", self.check_strategy),
            ("API Keys", self.check_api_keys),
            ("Model Servers", self.check_model_servers),
            ("Dependencies", self.check_dependencies),
            ("Disk Space", self.check_disk_space),
            ("Memory Database", self.check_memory_db),
        ]
        
        all_passed = True
        
        for name, check_func in checks:
            print(f"Checking {name}...")
            passed = check_func()
            
            if passed:
                print(f"   ✓ {name} OK\\n")
            else:
                print(f"   ✗ {name} FAILED\\n")
                all_passed = False
        
        # Summary
        print("=" * 70)
        
        if all_passed and not self.errors:
            print("✓ ALL CHECKS PASSED - System ready")
        else:
            print("✗ CHECKS FAILED - See issues below")
        
        if self.errors:
            print("\\n❌ Errors:")
            for error in self.errors:
                print(f"   • {error}")
        
        if self.warnings:
            print("\\n⚠️  Warnings:")
            for warning in self.warnings:
                print(f"   • {warning}")
        
        print("\\n" + "=" * 70 + "\\n")
        
        return all_passed and not self.errors
    
    def check_hardware(self) -> bool:
        """Check hardware and detect GPU."""
        hardware = detect_hardware()
        
        print(f"   GPU: {hardware.gpu_name or 'None'}")
        print(f"   VRAM: {hardware.vram_gb:.1f}GB")
        print(f"   Profile: {hardware.name}")
        
        if hardware.gpu_name is None:
            self.warnings.append("No GPU detected - will use cloud strategy")
        
        return True
    
    def check_strategy(self) -> bool:
        """Check strategy can be selected."""
        hardware = detect_hardware()
        strategy = get_strategy(hardware)
        
        if strategy is None:
            self.errors.append("Cannot select strategy")
            self.errors.append("Run setup wizard: python -m language_tutor.setup_wizard")
            return False
        
        print(f"   Strategy: {strategy['name']}")
        print(f"   Cost: ${strategy['cost_per_session']:.2f}/session")
        
        return True
    
    def check_api_keys(self) -> bool:
        """Check API keys if needed."""
        hardware = detect_hardware()
        strategy = get_strategy(hardware)
        
        if strategy is None:
            return True  # Skip if no strategy
        
        # Check if strategy needs API key
        needs_api = (
            strategy["planner"]["engine"] == "anthropic" or
            strategy["executor"]["engine"] == "anthropic"
        )
        
        if needs_api:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                self.errors.append("ANTHROPIC_API_KEY not set")
                self.errors.append("Get key from: https://console.anthropic.com/")
                self.errors.append("Set with: export ANTHROPIC_API_KEY='your-key'")
                return False
            
            print("   ✓ Anthropic API key found")
        else:
            print("   (No API key needed for local strategy)")
        
        return True
    
    def check_model_servers(self) -> bool:
        """Check if local model servers are running (if needed)."""
        hardware = detect_hardware()
        strategy = get_strategy(hardware)
        
        if strategy is None:
            return True
        
        # Check vLLM if executor is vllm
        if strategy["executor"]["engine"] == "vllm":
            try:
                import requests
                response = requests.get("http://localhost:8000/health", timeout=2)
                if response.status_code == 200:
                    print("   ✓ vLLM server running")
                else:
                    self.warnings.append("vLLM server not responding")
                    self.warnings.append("Start with: vllm serve <model> --port 8000")
            except Exception:
                self.warnings.append("vLLM server not running")
                self.warnings.append("Start with: vllm serve <model> --port 8000")
        
        # Check Ollama if planner is ollama
        if strategy["planner"]["engine"] == "ollama":
            try:
                import requests
                response = requests.get("http://localhost:11434/api/tags", timeout=2)
                if response.status_code == 200:
                    print("   ✓ Ollama server running")
                else:
                    self.warnings.append("Ollama server not responding")
                    self.warnings.append("Start with: ollama serve")
            except Exception:
                self.warnings.append("Ollama server not running")
                self.warnings.append("Start with: ollama serve")
        
        return True  # Warnings, not errors
    
    def check_dependencies(self) -> bool:
        """Check Python dependencies."""
        required = {
            "fastapi": "Web framework",
            "uvicorn": "Web server",
            "pydantic": "Data validation",
        }
        
        missing = []
        
        for module, description in required.items():
            try:
                __import__(module)
            except ImportError:
                missing.append(f"{module} ({description})")
        
        if missing:
            self.errors.append("Missing required packages:")
            for pkg in missing:
                self.errors.append(f"  - {pkg}")
            self.errors.append("Install with: pip install -r requirements.txt")
            return False
        
        print(f"   ✓ All {len(required)} core packages installed")
        return True
    
    def check_disk_space(self) -> bool:
        """Check available disk space."""
        import shutil
        
        stat = shutil.disk_usage(Path.home())
        free_gb = stat.free / (1024**3)
        
        print(f"   Free space: {free_gb:.1f}GB")
        
        if free_gb < 5:
            self.errors.append(f"Low disk space: {free_gb:.1f}GB")
            self.errors.append("Need at least 5GB for models and data")
            return False
        elif free_gb < 20:
            self.warnings.append(f"Disk space low: {free_gb:.1f}GB")
            self.warnings.append("Recommended: 20GB+ for comfort")
        
        return True
    
    def check_memory_db(self) -> bool:
        """Check memory database is writable."""
        test_dir = Path("data/memory/test")
        
        try:
            test_dir.mkdir(parents=True, exist_ok=True)
            test_file = test_dir / "test.txt"
            test_file.write_text("test")
            test_file.unlink()
            test_dir.rmdir()
            
            print("   ✓ Memory database directory writable")
            return True
        
        except Exception as e:
            self.errors.append(f"Cannot write to data/memory: {e}")
            return False


def main():
    """Run preflight check."""
    checker = LanguageTutorPreflight()
    passed = checker.run_all_checks()
    
    if passed:
        print("💡 System ready! Start with:")
        print("   python -m language_tutor.setup_wizard")
        print()
        sys.exit(0)
    else:
        print("❌ Fix errors above before starting")
        sys.exit(1)


if __name__ == "__main__":
    main()
'''
    
    (base_dir / "language_tutor" / "preflight_check.py").write_text(content)
    print("  ✓ Created preflight_check.py")


def create_setup_wizard(base_dir: Path):
    """Create setup_wizard.py for first-run configuration."""
    
    content = '''"""
Setup Wizard

Interactive setup for first-time configuration.
"""

import os
import sys
from pathlib import Path
from language_tutor.hardware_strategy import (
    detect_hardware,
    get_strategy,
    show_strategy_info,
    save_config,
)


def run_setup_wizard():
    """Interactive setup wizard."""
    
    print("\\n" + "=" * 70)
    print("LANGUAGE TUTOR SETUP WIZARD")
    print("=" * 70)
    
    print("\\nThis wizard will configure the language tutor for your system.\\n")
    
    # Step 1: Detect hardware
    print("Step 1: Detecting hardware...")
    hardware = detect_hardware()
    
    print(f"\\n  Detected:")
    print(f"    GPU: {hardware.gpu_name or 'None'}")
    print(f"    VRAM: {hardware.vram_gb:.1f}GB")
    print(f"    Profile: {hardware.name}")
    
    # Step 2: Check API key
    print("\\nStep 2: Checking API keys...")
    has_api_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    
    if has_api_key:
        print("  ✓ Anthropic API key found")
    else:
        print("  ⚠ Anthropic API key not found")
        
        if not hardware.can_run_7b:
            print("\\n  Your system requires an API key to run.")
            print("  Get one from: https://console.anthropic.com/")
            print("  Then: export ANTHROPIC_API_KEY='your-key-here'")
            
            response = input("\\n  Continue without API key? (y/n): ")
            if response.lower() != 'y':
                print("\\nSetup cancelled. Set API key and try again.")
                sys.exit(0)
    
    # Step 3: Select strategy
    print("\\nStep 3: Selecting strategy...")
    
    # Manual override option
    override = os.getenv("LANGUAGE_TUTOR_STRATEGY")
    if override:
        print(f"  Using override from env: {override}")
    
    strategy = get_strategy(hardware, override=override)
    
    if strategy is None:
        print("\\n❌ Cannot configure system.")
        print("   Check errors above and try again.")
        sys.exit(1)
    
    # Step 4: Show strategy and confirm
    print("\\nStep 4: Review configuration...")
    show_strategy_info(strategy, hardware)
    
    print("\\n" + "=" * 70)
    response = input("\\nProceed with this configuration? (y/n): ")
    
    if response.lower() != 'y':
        print("\\nSetup cancelled.")
        sys.exit(0)
    
    # Step 5: Save configuration
    print("\\nStep 5: Saving configuration...")
    config_path = Path.home() / ".language_tutor_config.json"
    save_config(strategy, hardware, config_path)
    
    # Step 6: Next steps
    print("\\n" + "=" * 70)
    print("✓ SETUP COMPLETE!")
    print("=" * 70)
    
    print("\\nNext steps:")
    print("  1. Start the application:")
    print("     python -m language_tutor.app")
    print()
    print("  2. Open browser:")
    print("     http://localhost:8080")
    print()
    
    if strategy["executor"]["engine"] == "vllm":
        print("  Note: Make sure vLLM server is running:")
        print("     vllm serve Qwen/Qwen2.5-7B-Instruct-AWQ --port 8000")
        print()
    
    if strategy["planner"]["engine"] == "ollama":
        print("  Note: Make sure Ollama server is running:")
        print("     ollama serve")
        print()


if __name__ == "__main__":
    run_setup_wizard()
'''
    
    (base_dir / "language_tutor" / "setup_wizard.py").write_text(content)
    print("  ✓ Created setup_wizard.py")


def create_fastapi_app(base_dir: Path):
    """Create app.py FastAPI application."""
    
    content = '''"""
FastAPI Application

Main web server for language tutor.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pathlib import Path

# Import routes (will create these)
# from language_tutor.routes import session, conversation

app = FastAPI(
    title="Language Tutor",
    description="AI-powered language learning with voice interaction",
    version="0.1.0",
)

# Mount static files
static_dir = Path(__file__).parent / "templates" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Basic health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}

# Serve main UI
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve main application UI."""
    template_path = Path(__file__).parent / "templates" / "index.html"
    
    if template_path.exists():
        return template_path.read_text()
    else:
        return """
        <html>
            <head><title>Language Tutor</title></head>
            <body>
                <h1>Language Tutor</h1>
                <p>Template not found. Creating minimal interface...</p>
                <p>TODO: Build UI</p>
            </body>
        </html>
        """

# Mount routes (TODO: uncomment when routes are created)
# app.include_router(session.router, prefix="/api/session", tags=["session"])
# app.include_router(conversation.router, prefix="/api/conversation", tags=["conversation"])


if __name__ == "__main__":
    import uvicorn
    
    print("Starting Language Tutor...")
    print("Open browser to: http://localhost:8080")
    
    uvicorn.run(
        "language_tutor.app:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
    )
'''
    
    (base_dir / "language_tutor" / "app.py").write_text(content)
    print("  ✓ Created app.py")


def create_basic_ui(base_dir: Path):
    """Create minimal web UI."""
    
    html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Language Tutor</title>
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    <div class="container">
        <header>
            <h1>🎓 Language Tutor</h1>
            <p>AI-powered language learning</p>
        </header>
        
        <main>
            <section class="language-selector">
                <h2>Select Language</h2>
                <button id="btn-spanish" class="language-btn">
                    🇪🇸 Spanish (Español)
                </button>
                <button id="btn-latin" class="language-btn">
                    📜 Latin (Latina)
                </button>
            </section>
            
            <section class="session-info" style="display: none;">
                <h2 id="session-title">Session</h2>
                <p id="session-status">Ready to start</p>
                <button id="btn-start-session" class="primary-btn">Start Session</button>
                <button id="btn-end-session" class="secondary-btn" style="display: none;">End Session</button>
            </section>
            
            <section class="chat-area" style="display: none;">
                <div id="chat-messages" class="chat-messages">
                    <!-- Messages will appear here -->
                </div>
                
                <div class="chat-input">
                    <textarea id="user-input" placeholder="Type your message..." rows="3"></textarea>
                    <button id="btn-send" class="primary-btn">Send</button>
                </div>
            </section>
        </main>
        
        <footer>
            <p>Phase 1: Text conversation • Voice coming in Phase 2</p>
        </footer>
    </div>
    
    <script llm_inspector_ui="/static/js/app.js"></script>
</body>
</html>
'''
    
    css_content = '''/* Language Tutor Styles */

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 20px;
}

.container {
    background: white;
    border-radius: 20px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    max-width: 800px;
    width: 100%;
    overflow: hidden;
}

header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 30px;
    text-align: center;
}

header h1 {
    font-size: 2.5rem;
    margin-bottom: 10px;
}

main {
    padding: 30px;
}

section {
    margin-bottom: 30px;
}

h2 {
    margin-bottom: 20px;
    color: #333;
}

.language-btn {
    display: block;
    width: 100%;
    padding: 20px;
    margin: 10px 0;
    font-size: 1.2rem;
    background: #f8f9fa;
    border: 2px solid #dee2e6;
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.3s;
}

.language-btn:hover {
    background: #667eea;
    color: white;
    border-color: #667eea;
    transform: translateY(-2px);
    box-shadow: 0 5px 15px rgba(102, 126, 234, 0.3);
}

.primary-btn, .secondary-btn {
    padding: 12px 24px;
    font-size: 1rem;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.3s;
    font-weight: 600;
}

.primary-btn {
    background: #667eea;
    color: white;
}

.primary-btn:hover {
    background: #5568d3;
    transform: translateY(-2px);
    box-shadow: 0 5px 15px rgba(102, 126, 234, 0.3);
}

.secondary-btn {
    background: #6c757d;
    color: white;
    margin-left: 10px;
}

.secondary-btn:hover {
    background: #5a6268;
}

.chat-messages {
    height: 400px;
    overflow-y: auto;
    border: 1px solid #dee2e6;
    border-radius: 10px;
    padding: 20px;
    margin-bottom: 20px;
    background: #f8f9fa;
}

.message {
    margin-bottom: 15px;
    padding: 15px;
    border-radius: 10px;
}

.message.user {
    background: #667eea;
    color: white;
    margin-left: 20%;
}

.message.assistant {
    background: white;
    border: 1px solid #dee2e6;
    margin-right: 20%;
}

.chat-input {
    display: flex;
    gap: 10px;
}

.chat-input textarea {
    flex: 1;
    padding: 12px;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    font-family: inherit;
    font-size: 1rem;
    resize: vertical;
}

footer {
    background: #f8f9fa;
    padding: 20px;
    text-align: center;
    color: #6c757d;
    border-top: 1px solid #dee2e6;
}
'''
    
    js_content = '''// Language Tutor Frontend

let currentLanguage = null;
let sessionActive = false;

// DOM elements
const languageSelector = document.querySelector('.language-selector');
const sessionInfo = document.querySelector('.session-info');
const chatArea = document.querySelector('.chat-area');
const sessionTitle = document.getElementById('session-title');
const sessionStatus = document.getElementById('session-status');
const btnStartSession = document.getElementById('btn-start-session');
const btnEndSession = document.getElementById('btn-end-session');
const chatMessages = document.getElementById('chat-messages');
const userInput = document.getElementById('user-input');
const btnSend = document.getElementById('btn-send');

// Event listeners
document.getElementById('btn-spanish').addEventListener('click', () => selectLanguage('spanish'));
document.getElementById('btn-latin').addEventListener('click', () => selectLanguage('latin'));
btnStartSession.addEventListener('click', startSession);
btnEndSession.addEventListener('click', endSession);
btnSend.addEventListener('click', sendMessage);
userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

function selectLanguage(language) {
    currentLanguage = language;
    
    languageSelector.style.display = 'none';
    sessionInfo.style.display = 'block';
    
    const languageNames = {
        'spanish': 'Spanish (Español)',
        'latin': 'Latin (Latina)'
    };
    
    sessionTitle.textContent = `${languageNames[language]} Session`;
    sessionStatus.textContent = 'Ready to start';
}

async function startSession() {
    // TODO: Call API to start session
    console.log('Starting session for:', currentLanguage);
    
    sessionActive = true;
    btnStartSession.style.display = 'none';
    btnEndSession.style.display = 'inline-block';
    sessionInfo.style.display = 'none';
    chatArea.style.display = 'block';
    
    // Add greeting
    addMessage('assistant', 'Hello! Ready to practice?');
    
    sessionStatus.textContent = 'Session active';
}

async function endSession() {
    // TODO: Call API to end session
    console.log('Ending session');
    
    sessionActive = false;
    btnStartSession.style.display = 'inline-block';
    btnEndSession.style.display = 'none';
    chatArea.style.display = 'none';
    sessionInfo.style.display = 'block';
    
    // Clear chat
    chatMessages.innerHTML = '';
    
    sessionStatus.textContent = 'Session ended';
}

async function sendMessage() {
    const message = userInput.value.trim();
    
    if (!message) return;
    
    // Add user message
    addMessage('user', message);
    userInput.value = '';
    
    // TODO: Call API to get response
    // For now, echo back
    setTimeout(() => {
        addMessage('assistant', `You said: "${message}"`);
    }, 500);
}

function addMessage(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    messageDiv.textContent = content;
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}
'''
    
    # Create files
    templates_dir = base_dir / "language_tutor" / "templates"
    static_dir = templates_dir / "static"
    
    (templates_dir / "index.html").write_text(html_content)
    (static_dir / "css" / "style.css").write_text(css_content)
    (static_dir / "js" / "app.js").write_text(js_content)
    
    print("  ✓ Created web UI templates")


def create_requirements(base_dir: Path):
    """Create requirements.txt."""
    
    content = '''# Language Tutor Requirements

# Core dependencies (already installed via llm-engine and memory-rag)
# These are listed for reference but should already be available

# Web framework
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-multipart>=0.0.6
websockets>=12.0

# Already from llm-engine
pydantic>=2.0.0
openai>=1.0.0
anthropic>=0.18.0
tiktoken>=0.5.0

# Already from memory-rag
chromadb>=0.4.0
sentence-transformers>=2.2.0
kuzu>=0.0.11

# Voice pipeline (Phase 2)
# faster-whisper>=1.0.0
# piper-tts>=1.2.0
# TTS>=0.22.0  # For XTTS v2

# Utilities
python-dotenv>=1.0.0
requests>=2.31.0
psutil>=5.9.0

# Development
pytest>=7.4.0
pytest-asyncio>=0.21.0
black>=23.0.0
'''
    
    (base_dir / "requirements.txt").write_text(content)
    print("  ✓ Created requirements.txt")


def create_pyproject_toml(base_dir: Path):
    """Create pyproject.toml."""
    
    content = '''[project]
name = "language-tutor"
version = "0.1.0"
description = "AI-powered language learning with voice interaction"
authors = [{name = "Jeff"}]
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.104",
    "uvicorn[standard]>=0.24",
    "python-multipart>=0.0.6",
    "websockets>=12.0",
    "pydantic>=2.0",
    "python-dotenv>=1.0",
    "requests>=2.31",
    "psutil>=5.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-asyncio>=0.21",
    "black>=23.0",
]

voice = [
    "faster-whisper>=1.0",
    "piper-tts>=1.2",
    "TTS>=0.22",
]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.black]
line-length = 100
target-version = ['py311']
'''
    
    (base_dir / "pyproject.toml").write_text(content)
    print("  ✓ Created pyproject.toml")


def create_readme(base_dir: Path):
    """Create README.md."""
    
    content = '''# Language Tutor

AI-powered language learning with voice interaction and personalized practice.

## Features

**Phase 1 (Current):**
- ✅ Hardware-adaptive (works on any system)
- ✅ Text-based conversation
- ✅ Memory persistence across sessions
- ✅ Session planning and summaries
- ✅ Cloud fallback for limited hardware

**Coming Soon:**
- 🚧 Voice interaction (STT/TTS)
- 🚧 Structured drills (vocabulary, conjugation)
- 🚧 Progress tracking
- 🚧 Latin support with pronunciation

## Quick Start

### 1. Install

```bash
cd ~/ai-projects/language_tutor
pip install -e .
```

### 2. Configure

```bash
# Run preflight check
python -m language_tutor.preflight_check

# Run setup wizard
python -m language_tutor.setup_wizard
```

### 3. Start

```bash
# Start the application
python -m language_tutor.app

# Open browser to:
# http://localhost:8080
```

## Architecture

Uses two core libraries:
- `llm-engine` - Unified LLM interface (vLLM/Ollama/Claude)
- `memory-rag` - Working/episodic/semantic memory with surprise filtering

See `HARDWARE_ADAPTIVE_README.md` for hardware strategy details.

## Development

### Run Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black language_tutor/
```

## Project Status

**Phase 1:** Foundation (text conversation) - IN PROGRESS
**Phase 2:** Voice pipeline - TODO
**Phase 3:** Drill system - TODO
**Phase 4:** Latin support - TODO
**Phase 5:** Production polish - TODO

## License

Personal project - not for distribution
'''
    
    (base_dir / "README.md").write_text(content)
    print("  ✓ Created README.md")


def create_gitignore(base_dir: Path):
    """Create .gitignore."""
    
    content = '''# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
env/
ENV/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Data directories
data/memory/
data/models/
data/voices/*.wav

# Configuration
.env
.language_tutor_config.json
.language_tutor_costs.json

# Logs
*.log
logs/

# OS
.DS_Store
Thumbs.db
'''
    
    (base_dir / ".gitignore").write_text(content)
    print("  ✓ Created .gitignore")


def main():
    """Main builder function."""
    
    # Determine paths
    if len(sys.argv) > 1:
        target_dir = Path(sys.argv[1]).expanduser().resolve()
    else:
        target_dir = Path.home() / "ai-projects" / "language_tutor"
    
    source_dir = Path("/mnt/user-data/outputs")
    spanish_tutor_dir = Path("/tmp/spanish_tutor")
    
    print("=" * 70)
    print("LANGUAGE TUTOR PROJECT BUILDER")
    print("=" * 70)
    print(f"\nTarget directory: {target_dir}")
    print(f"Source files: {source_dir}")
    
    # Confirm
    if target_dir.exists():
        response = input(f"\n⚠️  Directory exists. Continue? (y/n): ")
        if response.lower() != 'y':
            print("Aborted.")
            return
    
    # Create structure
    create_project_structure(target_dir)
    
    # Copy existing files
    copy_existing_files(target_dir, source_dir)
    
    # Create new files
    create_init_files(target_dir)
    create_config_file(target_dir)
    create_spanish_content(target_dir, spanish_tutor_dir)
    create_preflight_check(target_dir)
    create_setup_wizard(target_dir)
    create_fastapi_app(target_dir)
    create_basic_ui(target_dir)
    create_requirements(target_dir)
    create_pyproject_toml(target_dir)
    create_readme(target_dir)
    create_gitignore(target_dir)
    
    # Summary
    print("\n" + "=" * 70)
    print("✓ PROJECT CREATED SUCCESSFULLY")
    print("=" * 70)
    
    print(f"\nProject location: {target_dir}")
    print("\nNext steps:")
    print("  1. cd", target_dir)
    print("  2. pip install -e .")
    print("  3. python -m language_tutor.preflight_check")
    print("  4. python -m language_tutor.setup_wizard")
    print("  5. python -m language_tutor.app")
    print()


if __name__ == "__main__":
    main()

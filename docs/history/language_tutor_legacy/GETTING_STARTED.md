# Language Tutor - Getting Started

## ✅ What You Have

**Shared libraries in venv:**
```bash
source ~/venvs/your_venv/bin/activate
python -c "from llm_engine import VLLMEngine; print('✓ llm-engine')"
python -c "from memory_rag import ProjectMemory; print('✓ memory-rag')"
```

**Project code:**
```
~/PycharmProjects/language_tutor/
```

---

## 🚀 Quick Start

### 1. Open in PyCharm

```
PyCharm → File → Open → ~/PycharmProjects/language_tutor
```

### 2. Set Interpreter

```
Settings → Project: language_tutor → Python Interpreter
→ Select your venv (the one with llm-engine and memory-rag)
```

### 3. Run Preflight Check

```bash
# In PyCharm terminal:
python -m language_tutor.preflight_check
```

**Expected output:**
```
✓ Hardware Detection OK
✓ Strategy Selection OK
✓ API Keys OK (or warning if cloud needed)
✓ Dependencies OK
✓ Disk Space OK
✓ Memory Database OK
```

### 4. Run Setup Wizard

```bash
python -m language_tutor.setup_wizard
```

Creates `~/.language_tutor_config.json` with your hardware strategy.

### 5. Test It

```bash
# Quick test
python main_example.py --test

# OR start full app
python -m language_tutor.app
# Open: http://localhost:8080
```

---

## 📁 Project Structure

```
language_tutor/
├── language_tutor/          # Main package
│   ├── config.py           # Language profiles
│   ├── hardware_strategy.py # GPU detection
│   ├── engine_manager.py   # LLM management
│   ├── tutor_session.py    # Session orchestrator
│   ├── preflight_check.py  # System validation
│   ├── setup_wizard.py     # First-run setup
│   ├── app.py              # FastAPI server
│   │
│   ├── content/
│   │   └── spanish.py      # Spanish vocabulary
│   ├── routes/             # API endpoints (Phase 1 TODO)
│   ├── templates/          # Web UI
│   ├── voice/              # Voice pipeline (Phase 2)
│   └── drills/             # Drill system (Phase 3)
│
├── main_example.py         # Quick testing
├── data/                   # Runtime data
│   └── memory/             # ProjectMemory storage
│
└── README.md               # This file
```

---

## 🔧 Common Commands

```bash
# Navigate to project
cd ~/PycharmProjects/language_tutor

# Run checks
python -m language_tutor.preflight_check

# Configure
python -m language_tutor.setup_wizard

# Quick test
python main_example.py --test

# Start app
python -m language_tutor.app

# Run specific module
python -m language_tutor.config  # Test config loading
```

---

## 🐛 Troubleshooting

### "ModuleNotFoundError: No module named 'llm_engine'"

**Problem:** Libraries not in venv

**Solution:**
```bash
source ~/venvs/your_venv/bin/activate
pip install -e ~/ai-projects/core_infrastructure
pip install -e ~/ai-projects/memory_rag
```

### "ModuleNotFoundError: No module named 'language_tutor'"

**Problem:** Wrong directory

**Solution:**
```bash
cd ~/PycharmProjects/language_tutor  # Must be in project root
python -m language_tutor.app
```

### PyCharm Can't Find Imports

**Problem:** Wrong interpreter selected

**Solution:**
1. Settings → Project → Python Interpreter
2. Select your venv
3. Restart PyCharm

---

## 📚 Documentation

- **CORRECT_ARCHITECTURE_FINAL.md** - How everything fits together
- **HARDWARE_ADAPTIVE_README.md** - Hardware strategy details
- **PYCHARM_SETUP.md** - PyCharm tips and tricks

---

## 🎯 Phase 1 Status

**Working now:**
- ✅ Hardware detection
- ✅ Strategy selection
- ✅ Engine management
- ✅ Configuration system
- ✅ Preflight checks
- ✅ Setup wizard
- ✅ Basic web UI

**Next to implement:**
- 🚧 API routes (`routes/conversation.py`, `routes/session.py`)
- 🚧 Session planning (32B/Claude)
- 🚧 Conversation loop (7B/Claude)
- 🚧 Memory integration
- 🚧 End-to-end testing

**Future phases:**
- Phase 2: Voice (STT/TTS)
- Phase 3: Drills
- Phase 4: Latin support

---

## ✨ That's It!

**No installation needed. Just open in PyCharm and run.**

The project imports from your venv libraries automatically.

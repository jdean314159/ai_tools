# Language Tutor - Ready for PyCharm Development ✓

## ✅ What's Done

**Project created at:**
```
~/PycharmProjects/language_tutor/
```

**Installation script updated for your paths:**
```bash
~/ai-projects/core_infrastructure/     # llm-engine
~/ai-projects/memory_rag/             # memory-rag
~/PycharmProjects/language_tutor/     # this project
```

---

## 🚀 Next Steps (On Your System)

### 1. Open in PyCharm

```bash
# Open PyCharm
# File → Open → ~/PycharmProjects/language_tutor
```

### 2. Configure Python Interpreter

**In PyCharm:**
1. Settings → Project: language_tutor → Python Interpreter
2. Add Interpreter → Existing
3. Select your venv (e.g., `~/venvs/your_venv/bin/python`)

### 3. Install Packages

**In PyCharm Terminal:**
```bash
# Activate your venv first
source ~/venvs/your_venv/bin/activate

# Run install script
bash install_language_tutor.sh
```

**OR manually:**
```bash
pip install -e ~/ai-projects/core_infrastructure
pip install -e ~/ai-projects/memory_rag
pip install -e ~/PycharmProjects/language_tutor
```

### 4. Verify Installation

```bash
python -m language_tutor.preflight_check
```

**Expected output:**
```
✓ Hardware Detection OK
✓ Strategy Selection OK
✓ API Keys OK (or warning)
✓ Dependencies OK
✓ Disk Space OK
✓ Memory Database OK
```

### 5. Run Setup Wizard

```bash
python -m language_tutor.setup_wizard
```

This creates `~/.language_tutor_config.json` with your hardware strategy.

### 6. Test Basic Functionality

```bash
# Quick test
python main_example.py --test

# OR start full app
python -m language_tutor.app
# Then open: http://localhost:8080
```

---

## 📁 Files in Your Project

```
~/PycharmProjects/language_tutor/
├── PYCHARM_SETUP.md              ← PyCharm-specific guide
├── INSTALLATION_GUIDE.md         ← General installation
├── HARDWARE_ADAPTIVE_README.md   ← Strategy documentation
├── README.md                     ← Overview
│
├── install_language_tutor.sh     ← One-command install
├── main_example.py               ← Quick testing
│
├── language_tutor/               ← Main package
│   ├── config.py                 ← Language profiles
│   ├── hardware_strategy.py      ← GPU detection
│   ├── engine_manager.py         ← LLM engines
│   ├── tutor_session.py          ← Session orchestrator
│   ├── preflight_check.py        ← System validation
│   ├── setup_wizard.py           ← First-run setup
│   ├── app.py                    ← FastAPI web server
│   │
│   ├── content/
│   │   └── spanish.py            ← Spanish vocabulary
│   ├── routes/                   ← API endpoints (TODO)
│   ├── templates/                ← Web UI
│   ├── voice/                    ← Phase 2
│   └── drills/                   ← Phase 3
│
├── tests/                        ← Test suite
│   └── integration/
│
└── data/                         ← Runtime data
    ├── memory/                   ← ProjectMemory storage
    ├── voices/                   ← Voice samples
    └── models/                   ← Downloaded models
```

---

## 🎯 Development Workflow in PyCharm

### Code Navigation

- **Jump to definition:** Ctrl+Click (or Cmd+Click on Mac)
- **Find usages:** Alt+F7 (or Cmd+F7 on Mac)
- **Go to file:** Ctrl+Shift+N

**Works across all three packages!** You can jump from:
```python
# In language_tutor/tutor_session.py
from memory_rag import ProjectMemory  # ← Ctrl+Click jumps to source
```

### Running

**Create run configuration:**
1. Run → Edit Configurations → Add New → Python
2. **Script:** `language_tutor/app.py`
3. **Working dir:** `~/PycharmProjects/language_tutor`
4. Run with green play button

### Debugging

1. Set breakpoint in `tutor_session.py`
2. Run in debug mode (bug icon)
3. Step through code with F8
4. Can step into `memory_rag` and `llm_engine` code!

### Testing

**Run tests:**
- Right-click on `tests/` → Run
- Or: `pytest tests/` in terminal

---

## 📚 Documentation Reference

**Read these in order:**

1. **PYCHARM_SETUP.md** ← Start here (PyCharm-specific guide)
2. **INSTALLATION_GUIDE.md** ← Package installation details
3. **HARDWARE_ADAPTIVE_README.md** ← Hardware strategy system
4. **README.md** ← Project overview

---

## ⚡ Quick Commands

```bash
# In PyCharm Terminal (after activating venv):

# Install everything
bash install_language_tutor.sh

# Validate system
python -m language_tutor.preflight_check

# Configure
python -m language_tutor.setup_wizard

# Quick test
python main_example.py --test

# Start app
python -m language_tutor.app

# Run tests
pytest tests/
```

---

## 🎨 PyCharm Tips

### Enable Type Hints

Settings → Editor → Inspections → Python → Type Checker → ✓ Enable

### Auto-imports

Settings → Editor → General → Auto Import → ✓ Show import popup

### Code Style

Settings → Editor → Code Style → Python → Use PEP 8

### Terminal

View → Tool Windows → Terminal (or Alt+F12)

---

## 🔧 Phase 1 Status

**Completed:**
- ✅ Project structure
- ✅ Hardware detection
- ✅ Strategy system
- ✅ Engine management
- ✅ Configuration
- ✅ Preflight checks
- ✅ Setup wizard
- ✅ Basic web UI
- ✅ Spanish content

**Next (to complete Phase 1):**
- 🚧 API endpoints (`routes/conversation.py`, `routes/session.py`)
- 🚧 Wire routes to FastAPI app
- 🚧 Implement conversation loop
- 🚧 Test end-to-end

**Future phases:**
- Phase 2: Voice pipeline (STT/TTS)
- Phase 3: Drill system
- Phase 4: Latin support

---

## ✅ Ready to Start!

**The project is set up and ready for PyCharm development.**

**Next action on your system:**
1. Open PyCharm → `~/PycharmProjects/language_tutor`
2. Configure interpreter
3. Run: `bash install_language_tutor.sh`
4. Run: `python -m language_tutor.preflight_check`

**Then you're ready to start implementing Phase 1 features!** 🚀

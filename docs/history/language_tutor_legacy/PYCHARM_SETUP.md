# Language Tutor - PyCharm Development Setup

## Project Location

```
~/PycharmProjects/language_tutor/  ← Development location
```

## Installation for Development

### Step 1: Activate Your Virtual Environment

```bash
source ~/your_venv/bin/activate
```

### Step 2: Install All Three Packages

```bash
# Install core libraries from ai-projects
pip install -e ~/ai-projects/core_infrastructure  # llm-engine
pip install -e ~/ai-projects/memory_rag          # memory-rag

# Install language tutor from PyCharm directory
cd ~/PycharmProjects/language_tutor
pip install -e .
```

**OR use the automated script:**
```bash
cd ~/PycharmProjects/language_tutor
bash install_language_tutor.sh
```

### Step 3: Configure PyCharm

**Open Project:**
1. PyCharm → Open → `~/PycharmProjects/language_tutor`

**Set Interpreter:**
1. PyCharm → Settings → Project: language_tutor → Python Interpreter
2. Add Interpreter → Existing → Select your venv
   - Example: `~/venvs/your_venv/bin/python`
3. Apply → OK

**Verify Packages:**
In PyCharm's Python Packages tab, you should see:
- `llm-engine` (0.1.0) - editable install
- `memory-rag` (0.5.0) - editable install
- `language-tutor` (0.1.0) - editable install

### Step 4: Run Preflight Check

**In PyCharm Terminal:**
```bash
python -m language_tutor.preflight_check
```

---

## PyCharm Benefits

✅ **Code navigation** - Jump to definitions in llm-engine and memory-rag
✅ **Autocomplete** - IntelliSense works across all three packages
✅ **Debugging** - Set breakpoints in any package
✅ **Refactoring** - Rename, extract methods across packages
✅ **Type hints** - Full type checking for Pydantic models

---

## Running the Application

### From PyCharm Terminal:

```bash
# Run preflight check
python -m language_tutor.preflight_check

# Run setup wizard
python -m language_tutor.setup_wizard

# Run quick test
python main_example.py --test

# Run full application
python -m language_tutor.app
```

### As PyCharm Run Configuration:

**Create Run Configuration:**
1. Run → Edit Configurations
2. Add New → Python
3. **Name:** "Language Tutor"
4. **Script path:** `~/PycharmProjects/language_tutor/language_tutor/app.py`
5. **Working directory:** `~/PycharmProjects/language_tutor`
6. **Environment:** Add `ANTHROPIC_API_KEY` if using cloud strategy
7. Apply → OK

**Run:** Click green play button or `Shift+F10`

---

## Development Workflow

### Making Changes

**Edit files in PyCharm:**
- Changes to `language_tutor/*` → Effect immediately (editable install)
- Changes to `~/ai-projects/core_infrastructure/*` → Effect immediately
- Changes to `~/ai-projects/memory_rag/*` → Effect immediately

**No reinstall needed!** Just restart the application.

### Testing

**Run all tests:**
```bash
pytest tests/
```

**Run specific test:**
```bash
pytest tests/test_strategy.py::test_hardware_detection
```

**With PyCharm:**
- Right-click on test file → Run
- Debugging works with breakpoints

---

## Project Structure in PyCharm

```
language_tutor/                    ← Project root
├── language_tutor/               ← Main package
│   ├── __init__.py
│   ├── config.py                 ← Edit here
│   ├── hardware_strategy.py
│   ├── engine_manager.py
│   ├── tutor_session.py
│   ├── preflight_check.py
│   ├── setup_wizard.py
│   ├── app.py                    ← FastAPI app
│   ├── voice/                    ← Phase 2
│   ├── drills/                   ← Phase 3
│   ├── content/
│   │   └── spanish.py
│   ├── routes/                   ← Create API endpoints here
│   └── templates/                ← Web UI
│
├── tests/                        ← Test suite
├── data/                         ← Runtime data (gitignored)
├── main_example.py               ← Quick testing
├── pyproject.toml
├── requirements.txt
└── README.md
```

### External Packages (Also Navigable)

PyCharm can navigate to:
```
~/ai-projects/core_infrastructure/llm_engine/
~/ai-projects/memory_rag/memory_rag/
```

**Jump to definition** works across all three packages!

---

## Debugging Tips

### Debug Session Flow

1. Set breakpoint in `language_tutor/tutor_session.py`
2. Run in debug mode
3. Step into calls to `memory_rag.ProjectMemory`
4. PyCharm opens source from `~/ai-projects/memory_rag/`
5. Can set breakpoints there too!

### Debug Configuration

```python
# In app.py, add debug flag:
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "language_tutor.app:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="debug",  # ← Add this for verbose logging
    )
```

---

## Common PyCharm Tasks

### Add New File

1. Right-click on `language_tutor/routes/`
2. New → Python File
3. Name: `conversation.py`
4. PyCharm auto-creates with proper imports

### Refactor

1. Right-click on function/class
2. Refactor → Rename
3. PyCharm updates all references (even in other packages!)

### Find Usages

1. Right-click on `ProjectMemory`
2. Find Usages
3. Shows everywhere it's used across all three packages

### Run with Environment Variables

**In Run Configuration:**
1. Edit Configurations
2. Environment variables: `ANTHROPIC_API_KEY=sk-...`
3. Or use `.env` file (python-dotenv)

---

## Moving to Production Later

When ready to move to `~/ai-projects/`:

```bash
# Move the project
mv ~/PycharmProjects/language_tutor ~/ai-projects/

# Update PyCharm project location
# PyCharm → File → Open → ~/ai-projects/language_tutor

# Reinstall (new path)
pip install -e ~/ai-projects/language_tutor
```

**OR** keep it in PyCharmProjects - location doesn't matter for deployment!

---

## Quick Reference

**Location:** `~/PycharmProjects/language_tutor`

**Install:**
```bash
bash install_language_tutor.sh
```

**Run:**
```bash
python -m language_tutor.app
```

**Test:**
```bash
pytest tests/
```

**Debug:** Set breakpoints → `Shift+F9`

---

## Next Steps

1. ✅ Project in PyCharm
2. ✅ Install script updated
3. 🔧 Run installation
4. 🔧 Configure PyCharm interpreter
5. 🔧 Run preflight check
6. 🔧 Start development!

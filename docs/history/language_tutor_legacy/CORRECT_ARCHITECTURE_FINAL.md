# Language Tutor - Correct Architecture (FINAL)

## Your Setup - Clarified ✓

### Shared Libraries (In Venv)
```
~/venvs/your_venv/
  site-packages/
    ├── llm_engine/      ← Installed once, used by all projects
    └── memory_rag/      ← Installed once, used by all projects
```

**Install once:**
```bash
source ~/venvs/your_venv/bin/activate
pip install -e ~/ai-projects/core_infrastructure  # llm-engine
pip install -e ~/ai-projects/memory_rag          # memory-rag
```

### Projects (Just Source Code)
```
~/PycharmProjects/
  ├── language_tutor/    ← NOT installed, just code
  ├── photo_organizer/   ← NOT installed, just code
  └── future_project/    ← NOT installed, just code
```

**Each project:**
- Is just a folder with Python code
- Imports from the venv libraries
- No `pip install` needed
- Can be opened directly in PyCharm

---

## How Language Tutor Works

### Directory Structure
```
~/PycharmProjects/language_tutor/
├── language_tutor/          # Python package (has __init__.py)
│   ├── __init__.py
│   ├── config.py           # Local module
│   ├── hardware_strategy.py
│   ├── engine_manager.py
│   ├── tutor_session.py
│   ├── app.py
│   └── ...
│
├── main_example.py          # Run directly
├── README.md
└── data/                    # Runtime data
```

### Imports Work Like This
```python
# In any file in the project:

# Local imports (from this project folder)
from language_tutor.config import get_language_profile
from language_tutor.tutor_session import TutorSession

# Library imports (from venv)
from llm_engine import VLLMEngine, OllamaEngine
from memory_rag import ProjectMemory
```

Python finds modules in this order:
1. Current directory / package
2. PYTHONPATH
3. Venv site-packages ← Your libraries are here

---

## PyCharm Setup (Simple)

### 1. Open Project
```
PyCharm → File → Open → ~/PycharmProjects/language_tutor
```

### 2. Set Interpreter
```
Settings → Project → Python Interpreter → Select your venv
```

PyCharm will show installed packages:
- ✓ llm-engine (0.1.0) - editable
- ✓ memory-rag (0.5.0) - editable
- ✓ All their dependencies

### 3. Run Code
Just run any Python file:
- Right-click `main_example.py` → Run
- Or terminal: `python main_example.py`

**No installation step!**

---

## Running the Application

```bash
cd ~/PycharmProjects/language_tutor

# All these work directly:
python main_example.py --test
python -m language_tutor.preflight_check
python -m language_tutor.setup_wizard
python -m language_tutor.app
```

---

## Files You Can Ignore/Delete

These were created assuming you'd install the project (not needed):

### Optional (can delete):
- `pyproject.toml` - Only needed if you want to install the project
- `install_language_tutor.sh` - Only needed if you want to install the project
- `requirements.txt` - Libraries are already in venv

### Keep:
- `README.md` - Now updated for non-installed usage
- All `language_tutor/` code - This is your actual project
- `main_example.py` - Test/run script
- `data/` - Runtime data directory

---

## Development Workflow

### Making Changes
1. Edit files in PyCharm
2. Run directly - no reinstall needed
3. Changes take effect immediately

### Adding Dependencies
If you need a new library:
```bash
# Install in venv (not in project)
pip install some-new-library
```

Then import in your code:
```python
import some_new_library
```

### Testing
```bash
# Run tests directly
pytest tests/

# Or in PyCharm: right-click tests/ → Run
```

---

## Multiple Projects Pattern

This same pattern works for all your projects:

```
~/venvs/your_venv/          ← One venv with shared libraries

~/PycharmProjects/
  ├── language_tutor/       ← Imports from venv
  │   └── language_tutor/
  │       └── (imports llm_engine, memory_rag)
  │
  ├── photo_organizer/      ← Also imports from venv
  │   └── photo_organizer/
  │       └── (imports llm_engine, memory_rag)
  │
  └── voice_assistant/      ← Also imports from venv
      └── voice_assistant/
          └── (imports llm_engine, memory_rag)
```

**Benefits:**
- ✅ One set of libraries, many projects
- ✅ Update library once, all projects get it
- ✅ No installation complexity per project
- ✅ Easy to add new projects
- ✅ Clean separation

---

## Verification

### Check Libraries Are Available
```bash
cd ~/PycharmProjects/language_tutor
source ~/venvs/your_venv/bin/activate

python -c "
from llm_engine import VLLMEngine
from memory_rag import ProjectMemory
from language_tutor.config import get_language_profile
print('✓ All imports work')
"
```

### Check PyCharm Can See Everything
In PyCharm:
1. Open `language_tutor/tutor_session.py`
2. Ctrl+Click on `ProjectMemory` import
3. Should jump to `~/ai-projects/memory_rag/memory_rag/project_memory.py`

**If that works, you're all set!**

---

## Summary

**What you have:**
- ✅ llm-engine in venv (shared library)
- ✅ memory-rag in venv (shared library)
- ✅ language_tutor as project code (NOT installed)

**What you do:**
1. Open project in PyCharm
2. Set interpreter to your venv
3. Run code directly

**What you DON'T do:**
- ❌ Don't pip install the project
- ❌ Don't worry about pyproject.toml
- ❌ Don't run install scripts

**It's just regular Python code that imports from your venv!** 🎉

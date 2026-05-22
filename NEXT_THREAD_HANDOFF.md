# Next Thread Handoff — ai_tools

Last updated: 2026-05-22

## Current state

The engram freeze and rename is complete. All tests pass. See STATUS.md for
the full picture.

## Immediate next objective: engram_ui engine reconciliation

engram_ui imports from engram.engine.* which no longer exists. It is
currently broken. The migration target is llm_engines.

Before starting any code changes, write an ADR scoping this migration.
The key question is whether engram_ui should be a thin shim over
llm_engines or whether it warrants deeper redesign.

## Blast radius (from last session)

engram_ui/src/engram_ui/engine_factory.py:17
    from engram.engine import create_failover_engine

engram_ui/src/engram_ui/runtime_manager.py:23
    from engram.engine.config_loader import load_config

engram_ui/src/engram_ui/runtime_manager.py:141
    from engram.engine.runtime_status import build_llama_cpp_launch_command

engram_ui/src/engram_ui/app.py:29
    from engram.engine import load_config

engram_ui/src/engram_ui/app.py:31
    from engram.engine.model_discovery import list_ollama_models, list_vllm_models

engram_ui/src/engram_ui/app.py:40
    from engram.engine.runtime_status import (...)

engram_ui/src/engram_ui/model_management/profiles.py:12
    from engram.engine.model_manager import add_engine_to_profile

engram_ui/src/engram_ui/model_management/add_models.py:17
    from engram.engine.model_manager import (...)

engram_ui/src/engram_ui/model_management/add_models.py:33
    from engram.engine.runtime_status import (...)

engram_ui/src/engram_ui/model_management/_shared.py:19
    from engram.engine.model_manager import (...)

engram_ui/src/engram_ui/model_management/_shared.py:22
    from engram.engine.model_discovery import (...)

engram_ui/src/engram_ui/model_management/_shared.py:23
    from engram.engine.runtime_status import (...)

engram_ui/src/engram_ui/model_management/_shared.py:52
    import engram.engine  (used to resolve path to llm_engines.yaml)

engram_ui/src/engram_ui/model_management/inventory.py:14
    from engram.engine.model_manager import (...)

engram_ui/src/engram_ui/diagnostics_bridge.py:139
    import engram.engine  (used to resolve path to llm_engines.yaml)

engram_ui/src/engram_ui/diagnostics_bridge.py:169
    from engram.engine.model_manager import GPUInfo, SystemInfo


## Key mapping questions to resolve before coding

engram.engine.model_manager (add_engine_to_profile, GPUInfo, SystemInfo, etc.)
    Does llm_engines have equivalents, or does this logic move into engram_ui?

engram.engine.runtime_status (build_llama_cpp_launch_command, etc.)
    Launch command logic may need to live in engram_ui itself.

engram.engine.config_loader.load_config
    llm_engines has its own config_loader; check compatibility.

llm_engines.yaml path: currently resolved via engram.engine.__file__
    The file now lives at llm_engines/llm_engines/data/llm_engines.yaml.
    Use importlib.resources or a direct relative path.


## First commands in next thread

    cd ~/ai_tools
    git status --short --branch
    git log --oneline --decorate --max-count=6

    # Confirm engram_ui is broken as expected
    .venv/bin/python -c "import engram_ui" 2>&1 | head -5

    # Check what model_manager exports (key unknown)
    grep -n "^def \|^class \|GPUInfo\|SystemInfo\|add_engine" \
      llm_engines/llm_engines/*.py 2>/dev/null | grep -v test | head -20


## Minor cleanup still pending (low priority)

- get_stats() reports "backend": "engram_lite" — update string to "engram"
- inspection.py emits source_package="engram_lite" — update to "engram"
- Delete engram/src/engram_lite_facade_backup/ if it exists
- README.md package table and VISION.md sections 3.2/3.3 still describe the
  two-library world — update after engram_ui migration so docs reflect stable
  final state
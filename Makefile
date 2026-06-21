# ai_tools/Makefile
#
# Development workspace for the AI toolkit monorepo.
# Run from ~/ai_tools/.
#
# IMPORTANT: Always run 'make install' before running tests or any
# package code.  The packages use pip editable installs; the repo
# directory structure alone is not sufficient for imports to work.
#
# Usage:
#   make install          Install all packages in editable mode
#   make test             Run all offline unit tests
#   make test-ui          Run llm_inspector_ui tests
#   make test-diagnostics Run diagnostics_agent example tests
#   make test-integration Run cross-package integration tests
#   make test-live        Run live Ollama conformance tests
#   make smoke            Run the llm_engines smoke test
#   make clean            Remove build artifacts and caches

REPO_ROOT := $(CURDIR)
PYTHON ?= python3
VENV ?= $(REPO_ROOT)/.venv
VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV_PYTHON) -m pip
PIP := $(VENV_PIP)
TEST_PYTHON := $(VENV_PYTHON)

# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

.PHONY: venv install
venv:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PIP) install --upgrade pip

install: venv
	$(PIP) install -e './llm_harness_core[dev]'
	$(PIP) install -e './llm_engines[dev]'
	$(PIP) install -e './engram[dev]'
	$(PIP) install -e './llm_inspector[dev]'
	$(PIP) install -e './rag_lib[dev]'
	$(PIP) install -e './llm_inspector_ui[dev]'
	$(PIP) install -e './examples/language_tutor[dev]'   
	$(PIP) install -e './examples/diagnostics_agent[dev]'
	$(PIP) install -e './agent_lib[dev]'
	@echo ""
	@echo "Core packages installed in dependency order. Run 'make test-core', 'make test-agent', 'make test-rag', 'make test-integration', 'make test-tutor', or 'make test-diagnostics' to verify."
	
.PHONY: install-gpu
install-gpu: install
	$(PIP) install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
	$(PIP) install -e './llm_engines[huggingface,optimizations]'
	CMAKE_ARGS="-DGGML_CUDA=on" $(PIP) install llama-cpp-python
	
# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

.PHONY: test
test: test-core

.PHONY: test-core
test-core:
	cd llm_harness_core && $(TEST_PYTHON) -m pytest tests/ -v
	cd llm_engines && $(TEST_PYTHON) -m pytest tests/ \
		-m "not ollama and not anthropic and not openai and not vllm and not slow" \
		-v
	$(TEST_PYTHON) -m pytest engram/tests/ -v
	cd llm_inspector && $(TEST_PYTHON) -m pytest tests/ -v
	cd llm_inspector_ui && $(TEST_PYTHON) -m pytest tests/ -v
	cd agent_lib && $(TEST_PYTHON) -m pytest tests/ -v
	cd rag_lib && $(TEST_PYTHON) -m pytest tests/ -v

.PHONY: test-agent
test-agent:
	cd agent_lib && $(TEST_PYTHON) -m pytest tests/ -v

.PHONY: test-rag
test-rag:
	cd rag_lib && $(TEST_PYTHON) -m pytest tests/ -v

.PHONY: test-ui
test-ui:
	cd llm_inspector_ui && $(TEST_PYTHON) -m pytest tests/ -v

.PHONY: test-integration
test-integration:
	$(TEST_PYTHON) -m pytest integration_tests/ -v

.PHONY: test-tutor
test-tutor:
	cd examples/language_tutor && $(TEST_PYTHON) -m pytest test_language_tutor.py -v

.PHONY: test-diagnostics
test-diagnostics:
	cd examples/diagnostics_agent && $(TEST_PYTHON) -m pytest tests/ -v

.PHONY: eval-fp
eval-fp:
	cd examples/diagnostics_agent && $(TEST_PYTHON) \
		scripts/run_fp_eval.py --backend ollama --model qwen3.6:27b

.PHONY: test-fp-gate
test-fp-gate:
	cd examples/diagnostics_agent && $(TEST_PYTHON) -m pytest \
		tests/test_fp_gate.py -m ollama --gate-model qwen3.6:27b -v

.PHONY: test-live
test-live:
	cd llm_engines && $(TEST_PYTHON) -m pytest tests/contract_tests/ \
		--backend ollama --model qwen3:8b -v

.PHONY: test-live-embed
test-live-embed:
	cd llm_engines && $(TEST_PYTHON) -m pytest tests/contract_tests/ \
		--backend ollama --model qwen3:8b \
		--embed-model nomic-embed-text -v

.PHONY: test-all
test-all: test-core test-integration test-agent test-rag test-tutor test-diagnostics

.PHONY: run-diagnostics
# Streamlit UI for the diagnostics agent. Requires diagnostics_agent[ui].
run-diagnostics:
	cd examples/diagnostics_agent && $(TEST_PYTHON) -m streamlit run \
		src/diagnostics_agent/ui/app.py

.PHONY: run-inspector
# Streamlit workbench for llm_inspector_ui.
run-inspector:
	$(TEST_PYTHON) -m llm_inspector_ui
.PHONY: test-ml
test-ml: venv
	cd llm_engines && $(TEST_PYTHON) -m pytest tests/test_optimizations.py -v	

# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

.PHONY: smoke
smoke:
	cd llm_engines && $(TEST_PYTHON) scripts/smoke_test.py

.PHONY: smoke-anthropic
smoke-anthropic:
	cd llm_engines && $(TEST_PYTHON) scripts/smoke_test.py --anthropic

.PHONY: smoke-openai
smoke-openai:
	cd llm_engines && $(TEST_PYTHON) scripts/smoke_test.py --openai
	


# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------

.PHONY: lint
lint:
	$(TEST_PYTHON) -m mypy llm_engines/src/llm_engines/ \
		--config-file llm_engines/pyproject.toml \
		--ignore-missing-imports --no-error-summary

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

.PHONY: clean
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "Clean."

.PHONY: clean-all
clean-all: clean
	find . -type d -name ".idea" -exec rm -rf {} + 2>/dev/null || true

.PHONY: clean-review
clean-review: clean-all
	find . -type d -name ".git" -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type f \( -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" -o -name "*.db-*" -o -name "*.sqlite-*" -o -name "*.sqlite3-*" -o -name "*.bak" \) -delete 2>/dev/null || true
	rm -rf models engram/data/memory llm_inspector_ui/data 2>/dev/null || true
	@echo "Review bundle workspace cleaned."

.PHONY: check-hygiene
check-hygiene: clean
	$(VENV_PYTHON) scripts/check_publication_hygiene.py
	$(VENV_PYTHON) scripts/check_teaching_artifacts.py

.PHONY: check-decisions
check-decisions:
	$(VENV_PYTHON) scripts/validate_decision_history.py

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

.PHONY: help
help:
	@echo ""
	@echo "ai_tools monorepo — available targets:"
	@echo ""
	@echo "  make install          Install all packages (editable)"
	@echo "  make install-gpu      Install + GPU extras (llama.cpp CUDA, torch)"
	@echo ""
	@echo "  make test             Offline unit tests (no services needed)"
	@echo "  make test-agent       Agent kernel tests"
	@echo "  make test-rag         rag_lib unit tests"
	@echo "  make test-ui          llm_inspector_ui tests"
	@echo "  make test-diagnostics diagnostics_agent example tests"
	@echo "  make eval-fp          Report diagnostics interpretation calibration"
	@echo "  make test-fp-gate     Run live diagnostics FP/recall gate"
	@echo "  make test-integration Cross-package integration tests"
	@echo "  make test-live        Live Ollama conformance (ollama serve required)"
	@echo "  make test-live-embed  Live Ollama + embedding model tests"
	@echo "  make test-all         Offline + integration tests"
	@echo ""
	@echo "  make run-diagnostics  Launch the diagnostics_agent Streamlit UI (port 8501)"
	@echo "  make run-inspector    Launch the llm_inspector_ui Streamlit workbench (port 8501)"
	@echo ""
	@echo "  make smoke            Full environment smoke test"
	@echo "  make smoke-anthropic  Smoke test + Anthropic API"
	@echo "  make smoke-openai     Smoke test + OpenAI API"
	@echo ""
	@echo "  make lint             mypy type check"
	@echo "  make check-decisions  Validate ADR decision-history metadata"
	@echo "  make clean            Remove build artifacts"
	@echo "  make clean-all        Remove build artifacts + IDE files"
	@echo "  make clean-review     Remove caches, dbs, local data, and VCS residue for review bundles"
	@echo ""

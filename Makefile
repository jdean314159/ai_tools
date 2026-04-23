# ai_tools/Makefile
#
# Development workspace for the AI toolkit monorepo.
# Run from ~/ai_tools/.
#
# Usage:
#   make install          Install all packages in editable mode
#   make test             Run all offline unit tests
#   make test-integration Run cross-package integration tests
#   make test-live        Run live Ollama conformance tests
#   make smoke            Run the llm_engines smoke test
#   make clean            Remove build artifacts and caches

PYTHON := python3
VENV   := $(HOME)/ai-env/bin/python

# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

.PHONY: install
install:
	pip install -e llm_harness_core/[dev]
	pip install -e engram_lite/[dev]
	pip install -e llm_engines/[dev]
	pip install -e engram/
	pip install -e llm_inspector/[dev]
	pip install -e agent_lib/[dev]
	pip install -e rag_lib/[dev]
	pip install -e language_tutor/[dev]
	@echo ""
	@echo "Core packages installed. Run 'make test-core', 'make test-agent', 'make test-rag', 'make test-integration', or 'make test-tutor' to verify."

.PHONY: install-gpu
install-gpu: install
	CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python
	pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

.PHONY: test
test: test-core

.PHONY: test-core
test-core:
	cd llm_harness_core && $(PYTHON) -m pytest tests/ -v
	cd llm_engines && $(PYTHON) -m pytest tests/ \
		-m "not ollama and not anthropic and not openai and not vllm and not slow" \
		-v
	cd engram_lite && $(PYTHON) -m pytest tests/ -v
	cd llm_inspector && $(PYTHON) -m pytest tests/ -v
	cd agent_lib && $(PYTHON) -m pytest tests/ -v
	cd rag_lib && PYTHONPATH=src $(PYTHON) -m pytest tests/ -v

.PHONY: test-agent
test-agent:
	cd agent_lib && $(PYTHON) -m pytest tests/ -v

.PHONY: test-rag
test-rag:
	cd rag_lib && PYTHONPATH=src $(PYTHON) -m pytest tests/ -v

.PHONY: test-integration
test-integration:
	$(PYTHON) -m pytest integration_tests/ -v

.PHONY: test-tutor
test-tutor:
	cd language_tutor && $(PYTHON) -m pytest tests/ -v

.PHONY: test-live
test-live:
	cd llm_engines && $(PYTHON) -m pytest tests/contract_tests/ \
		--backend ollama --model qwen3:8b -v

.PHONY: test-live-embed
test-live-embed:
	cd llm_engines && $(PYTHON) -m pytest tests/contract_tests/ \
		--backend ollama --model qwen3:8b \
		--embed-model nomic-embed-text -v

.PHONY: test-all
test-all: test-core test-integration test-agent test-rag test-tutor

# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

.PHONY: smoke
smoke:
	cd llm_engines && $(PYTHON) scripts/smoke_test.py

.PHONY: smoke-anthropic
smoke-anthropic:
	cd llm_engines && $(PYTHON) scripts/smoke_test.py --anthropic

.PHONY: smoke-openai
smoke-openai:
	cd llm_engines && $(PYTHON) scripts/smoke_test.py --openai

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------

.PHONY: lint
lint:
	cd llm_engines && $(PYTHON) -m mypy llm_engines/ contracts/ \
		--ignore-missing-imports --no-error-summary 2>&1 | tail -5

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
	@echo "  make test-integration Cross-package integration tests"
	@echo "  make test-live        Live Ollama conformance (ollama serve required)"
	@echo "  make test-live-embed  Live Ollama + embedding model tests"
	@echo "  make test-all         Offline + integration tests"
	@echo ""
	@echo "  make smoke            Full environment smoke test"
	@echo "  make smoke-anthropic  Smoke test + Anthropic API"
	@echo "  make smoke-openai     Smoke test + OpenAI API"
	@echo ""
	@echo "  make lint             mypy type check"
	@echo "  make clean            Remove build artifacts"
	@echo "  make clean-all        Remove build artifacts + IDE files"
	@echo "  make clean-review     Remove caches, dbs, local data, and VCS residue for review bundles"
	@echo ""

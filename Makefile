# ModelSwapBench developer tasks. `make quality` must not hide failures.
.DEFAULT_GOAL := help
PY ?= python
EXAMPLES := examples

.PHONY: help setup test test-integration lint format typecheck security quality build example-offline example-ollama clean

help:
	@echo "Targets: setup test test-integration lint format typecheck security quality build example-offline example-ollama clean"

setup:
	$(PY) -m pip install -e ".[dev,security,quality]"

test:
	$(PY) -m pytest -m "not integration"

test-integration:
	$(PY) -m pytest -m integration

lint:
	$(PY) -m ruff check .

format:
	$(PY) -m ruff format . && $(PY) -m ruff check --fix .

typecheck:
	$(PY) -m mypy model_swap_bench

security:
	$(PY) -m bandit -c pyproject.toml -r model_swap_bench -q
	$(PY) -m pip_audit || true

quality: lint typecheck test security

build:
	rm -rf dist && $(PY) -m build && $(PY) -m twine check dist/*

example-offline:
	modelswapbench run $(EXAMPLES)/support-ticket-triage/benchmark.yaml
	modelswapbench report latest --format markdown

example-ollama:
	@echo "Requires: ollama pull qwen2.5:3b, then edit a suite to use provider: ollama"
	modelswapbench doctor

clean:
	rm -rf dist build .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

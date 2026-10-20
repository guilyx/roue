# Developer shortcuts. Run `make help` for the list.
#
# The venv uses the system Python with --system-site-packages so PyGObject,
# GTK 4 and libadwaita come from your distribution (they can't be pip-installed).

PYTHON ?= /usr/bin/python3
VENV   ?= .venv
BIN    := $(VENV)/bin
DEV_PACKAGES := pytest pytest-cov ruff mypy types-PyYAML markdown

.DEFAULT_GOAL := help
.PHONY: help dev test test-fast lint fmt typecheck check site deb run clean

help: ## Show this help
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  \033[1m%-10s\033[0m %s\n", $$1, $$2}'

$(BIN)/python:
	@if command -v uv >/dev/null 2>&1; then \
		uv venv --python $(PYTHON) --system-site-packages $(VENV); \
	else \
		$(PYTHON) -m venv --system-site-packages $(VENV); \
	fi

dev: $(BIN)/python ## Create .venv with an editable install and dev tools
	@if command -v uv >/dev/null 2>&1; then \
		uv pip install --python $(BIN)/python -e . --group dev; \
	else \
		$(BIN)/python -m pip install --upgrade pip; \
		$(BIN)/python -m pip install -e . $(DEV_PACKAGES); \
	fi
	@echo "Ready. Try: $(BIN)/roue doctor"

test: ## Run the full test suite (needs ffmpeg, vips, gs... for conversion tests)
	$(BIN)/pytest

test-fast: ## Skip slow conversions (LibreOffice, two-pass video)
	$(BIN)/pytest -m "not slow"

lint: ## Lint and check formatting
	$(BIN)/ruff check src tests scripts
	$(BIN)/ruff format --check src tests scripts

fmt: ## Format and auto-fix
	$(BIN)/ruff format src tests scripts
	$(BIN)/ruff check --fix src tests scripts

typecheck: ## Type-check the engine, CLI and integrations
	$(BIN)/mypy

check: lint typecheck test ## Everything CI runs on the code

site: ## Build the website and docs into website/
	$(BIN)/python scripts/build_site.py

deb: ## Build dist/roue_<version>_all.deb
	packaging/deb/build.sh

run: ## Open the drop panel from this checkout
	$(BIN)/roue panel

clean: ## Remove build and cache files
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -name '__pycache__' -type d -prune -not -path './$(VENV)/*' -exec rm -rf {} +

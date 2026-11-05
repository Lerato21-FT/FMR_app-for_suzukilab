# Run from Git Bash on the Windows lab computer (GNU Make 4.4+).
SHELL := sh
.DEFAULT_GOAL := help

-include .env
export

PYTHON_LAUNCHER ?= py -3.14
VENV := .venv
PY := $(VENV)/Scripts/python.exe
INSTALLED := $(VENV)/.installed
UV_VERSION := 0.9.15
PLOTLY_VERSION := 2.35.2
PLOTLY_SHA256 := 6d21266ce1bd7d9e5ab4e115989c70c20de0382fd973a8f26ab58619eba4d603
PLOTLY_URL := https://cdn.plot.ly/plotly-$(PLOTLY_VERSION).min.js
VENDOR := src/web/vendor/plotly.min.js
FMR_PORT ?= 8765
TEST_PATHS ?= tests
FORMAT_PATHS ?= src tests
SMOKE := tests/2026-11-04/smoke_check.py

# Keep every tool cache inside the repository.
export PIP_CACHE_DIR := $(CURDIR)/.cache/pip
export UV_CACHE_DIR := $(CURDIR)/.cache/uv
export PIP_DISABLE_PIP_VERSION_CHECK := 1
export PYTHONDONTWRITEBYTECODE := 1

.PHONY: help install lock vendor run test lint fmt smoke verify hardware-check review fresh-verify clean

help:
	@printf '%s\n' \
	'Everyday:' \
	'  install         Create .venv and install the locked dependencies' \
	'  run             Start the app at http://127.0.0.1:$(FMR_PORT) (Ctrl+C stops it)' \
	'  verify          Lint, tests and API smoke check (simulated instruments)' \
	'  clean           Remove .venv, caches and generated files (keeps data/ and .env)' \
	'' \
	'Developing:' \
	'  test            Run pytest (TEST_PATHS=... selects files)' \
	'  lint            Ruff checks and format check, changing nothing' \
	'  fmt             Format Python in place (FORMAT_PATHS=... selects files)' \
	'  smoke           Start the app, run a short simulated sweep over HTTP, stop' \
	'  vendor          Fetch the pinned Plotly file and check its hash' \
	'  hardware-check  Identify the real instruments (*IDN?) without changing outputs' \
	'  review          Check patch whitespace and show git status' \
	'  fresh-verify    Clone the committed branch into .cache/ and run verify' \
	'' \
	'Dependencies:' \
	'  lock            Regenerate requirements.lock after editing pyproject.toml'

$(PY):
	$(PYTHON_LAUNCHER) -m venv $(VENV)

$(INSTALLED): requirements.lock | $(PY)
	$(PY) -m pip install --require-hashes --no-deps -r requirements.lock
	@touch $(INSTALLED)

install: $(INSTALLED)

lock: | $(PY)
	$(PY) -m pip install uv==$(UV_VERSION)
	$(PY) -m uv pip compile pyproject.toml --extra dev --generate-hashes \
		--python-version 3.14 --python-platform x86_64-pc-windows-msvc \
		--output-file requirements.lock

$(VENDOR):
	@mkdir -p src/web/vendor .cache
	curl --fail --silent --show-error --location $(PLOTLY_URL) --output .cache/plotly.download
	@actual=$$(sha256sum .cache/plotly.download | cut -d ' ' -f 1); \
	if [ "$$actual" != "$(PLOTLY_SHA256)" ]; then \
		echo "Plotly hash mismatch: expected $(PLOTLY_SHA256), got $$actual"; exit 1; \
	fi
	mv .cache/plotly.download $(VENDOR)

vendor: $(VENDOR)

run: install vendor
	$(PY) -m uvicorn app.api:app --app-dir src --host 127.0.0.1 --port $(FMR_PORT)

test: install
	FMR_INSTRUMENTS=simulated $(PY) -m pytest $(TEST_PATHS)

lint: install
	$(PY) -m ruff check src tests
	$(PY) -m ruff format --check src tests

fmt: install
	$(PY) -m ruff format $(FORMAT_PATHS)

smoke: install vendor
	FMR_INSTRUMENTS=simulated PYTHONPATH=src $(PY) $(SMOKE)

verify: lint test smoke

hardware-check: install
	FMR_INSTRUMENTS=hardware PYTHONPATH=src $(PY) -m app.hardware_check

review:
	git diff --check
	git status --short --branch
	git diff --stat

fresh-verify:
	@mkdir -p .cache
	@set -eu; \
	checkout=$$(mktemp -d "$(CURDIR)/.cache/fresh-verify.XXXXXX"); \
	git clone --quiet --no-hardlinks . "$$checkout"; \
	$(MAKE) -C "$$checkout" verify

clean:
	rm -rf .venv .cache .pytest_cache .ruff_cache src/web/vendor artifacts
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +

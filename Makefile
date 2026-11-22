# Project commands. PORT defaults to $HN_PORT, then 8000.
PORT ?= $(or $(HN_PORT),8000)
UV := uv

.PHONY: setup serve test lint fmt check-text check-claims check-ui grade demo ui-audit check-secrets gate-fast gate-full eval

setup:
	$(UV) sync -q

serve: setup
	$(UV) run uvicorn app.main:app --host 127.0.0.1 --port $(PORT)

test: setup
	timeout 1200 $(UV) run pytest -q -x

lint: setup
	$(UV) run ruff check .

fmt: setup
	$(UV) run ruff check --fix . && $(UV) run ruff format .

check-text:
	$(UV) run python scripts/check_text.py

check-claims:
	$(UV) run python scripts/check_claims.py

check-ui:
	$(UV) run python scripts/check_ui.py

grade:
	$(UV) run python scripts/grade_done.py

# Evaluations write metrics.json (the only writer). `make eval ONLY=smsr` runs one of them.
eval: setup
	$(UV) run python scripts/evaluate.py $(ONLY)

# The golden path once in headless Chrome, short pauses, no video. Part of gate-fast: the demo is a test.
demo: setup
	@if [ -n "$(HN_SKIP_DEMO)" ]; then echo "DEMO SKIPPED (HN_SKIP_DEMO)"; else timeout 300 $(UV) run python scripts/run_demo.py; fi

# The jury's view at 1366x768, 1920x1080 and 390x844: overflow, overlaps, tap targets, font size,
# leftover lorem/TODO/undefined/NaN, English labels, console errors, failed requests, axe (WCAG 2.1 AA).
ui-audit: setup
	@if [ -n "$(HN_SKIP_DEMO)" ]; then echo "UI AUDIT SKIPPED (HN_SKIP_DEMO)"; else timeout 600 $(UV) run python scripts/ui_audit.py; fi

check-secrets:
	$(UV) run python scripts/check_secrets.py

# Lint, tests, text and claims checks and UI rules. Target < 90 s. The demo scenes run in gate-full (owner decision 22.11: gates were the bottleneck).
gate-fast: lint test check-text check-claims check-ui
	@echo "GATE OK"

# gate-fast plus the UI audit at three screen sizes and the secrets scan.
gate-full: gate-fast demo ui-audit check-secrets
	@echo "GATE-FULL OK"

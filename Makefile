.PHONY: init dev test seed-demo

init:
	python3 -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt
	@test -f .env || cp .env.example .env

dev:
	./scripts/dev.sh

test:
	./scripts/test.sh

seed-demo:
	@if [ -z "$(FALLBACK_WEBHOOK)" ]; then \
		echo "Usage: make seed-demo FALLBACK_WEBHOOK=<url> [ETF_WEBHOOK=<url>]"; \
		exit 1; \
	fi
	./scripts/seed_demo_rules.sh "$(FALLBACK_WEBHOOK)" "$(ETF_WEBHOOK)"

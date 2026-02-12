#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

if [ -z "${1:-}" ]; then
  echo "Usage: scripts/seed_demo_rules.sh <fallback_webhook_url> [--include-etf-example [etf_webhook_url]]"
  exit 1
fi

FALLBACK_WEBHOOK="$1"
INCLUDE_ETF_FLAG=""
ETF_WEBHOOK="${3:-https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=fake-etf-demo-key}"

if [ "${2:-}" = "--include-etf-example" ]; then
  INCLUDE_ETF_FLAG="--include-etf-example"
fi

exec .venv/bin/python -m app.seed_rules --fallback-webhook "$FALLBACK_WEBHOOK" $INCLUDE_ETF_FLAG --etf-webhook "$ETF_WEBHOOK"

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
  echo "Usage: scripts/seed_demo_rules.sh <fallback_webhook_url> [etf_webhook_url]"
  exit 1
fi

FALLBACK_WEBHOOK="$1"
ETF_WEBHOOK="${2:-https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=fake-etf-demo-key}"

exec .venv/bin/python -m app.seed_rules --fallback-webhook "$FALLBACK_WEBHOOK" --etf-webhook "$ETF_WEBHOOK"

#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/signal-router}"
SERVICE_NAME="${SERVICE_NAME:-signal-router}"
BRANCH="${BRANCH:-main}"
SKIP_TESTS="${SKIP_TESTS:-0}"

cd "$APP_DIR"

echo "[deploy] app dir: $APP_DIR"
echo "[deploy] branch: $BRANCH"

echo "[deploy] fetching latest code..."
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

echo "[deploy] ensuring virtualenv and deps..."
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt

if [ "$SKIP_TESTS" != "1" ]; then
  echo "[deploy] running tests..."
  if [ -x ./scripts/test.sh ]; then
    ./scripts/test.sh
  else
    .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
  fi
else
  echo "[deploy] skipping tests (SKIP_TESTS=1)"
fi

echo "[deploy] restarting service: $SERVICE_NAME"
sudo systemctl daemon-reload
sudo systemctl restart "$SERVICE_NAME"

sleep 1

echo "[deploy] service status:"
sudo systemctl --no-pager --full status "$SERVICE_NAME" | sed -n '1,20p'

echo "[deploy] health check:"
if command -v curl >/dev/null 2>&1; then
  curl -fsS -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8000/ || true
else
  echo "curl not found, skipped local health check"
fi

echo "[deploy] done"

#!/bin/bash
set -euo pipefail

INSTALL_ROOT="${HOME}/Library/Application Support/FeishuVideoExtractor"
ENV_PATH="$INSTALL_ROOT/backend.env"

if [ ! -f "$ENV_PATH" ]; then
  printf 'Missing config: %s\n' "$ENV_PATH" >&2
  exit 1
fi

set -a
. "$ENV_PATH"
set +a

cd "$INSTALL_ROOT/backend"
exec "$INSTALL_ROOT/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000


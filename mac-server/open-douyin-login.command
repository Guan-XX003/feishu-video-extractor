#!/bin/bash
set -euo pipefail

PROFILE_ROOT="${HOME}/Library/Application Support/FeishuVideoExtractor/browser-profile"
ENV_PATH="${HOME}/Library/Application Support/FeishuVideoExtractor/backend.env"
BROWSER="edge"

if [ -f "$ENV_PATH" ]; then
  CONFIGURED_BROWSER="$(sed -n 's/^COOKIES_FROM_BROWSER=//p' "$ENV_PATH" | head -n 1)"
  if [ -n "$CONFIGURED_BROWSER" ]; then
    BROWSER="$CONFIGURED_BROWSER"
  fi
fi

mkdir -p "$PROFILE_ROOT/Default"
if [ "$BROWSER" = "chrome" ]; then
  APP_NAME="Google Chrome"
else
  APP_NAME="Microsoft Edge"
fi

open -na "$APP_NAME" --args \
  --user-data-dir="$PROFILE_ROOT" \
  --profile-directory=Default \
  --no-first-run \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  https://www.douyin.com/

printf '%s\n' "A dedicated $APP_NAME window was opened. Log in to Douyin there, then close that dedicated window."

#!/bin/bash
set -euo pipefail

if [ "$#" -ne 1 ] || [[ "$1" != https://* ]]; then
  printf 'Usage: %s https://video-api.example.com\n' "$0" >&2
  exit 2
fi

INSTALL_ROOT="${HOME}/Library/Application Support/FeishuVideoExtractor"
ENV_PATH="$INSTALL_ROOT/backend.env"
PLIST_PATH="${HOME}/Library/LaunchAgents/com.growing.feishu-video-extractor.plist"
NEW_URL="${1%/}"

if [ ! -f "$ENV_PATH" ]; then
  printf 'Missing config: %s\n' "$ENV_PATH" >&2
  exit 1
fi

TEMP_PATH="$(mktemp)"
awk -v value="$NEW_URL" '
  BEGIN { replaced = 0 }
  /^PUBLIC_BASE_URL=/ { print "PUBLIC_BASE_URL=" value; replaced = 1; next }
  { print }
  END { if (!replaced) print "PUBLIC_BASE_URL=" value }
' "$ENV_PATH" > "$TEMP_PATH"
chmod 600 "$TEMP_PATH"
mv "$TEMP_PATH" "$ENV_PATH"

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
launchctl kickstart -k "gui/$(id -u)/com.growing.feishu-video-extractor"
printf 'Updated PUBLIC_BASE_URL=%s\n' "$NEW_URL"


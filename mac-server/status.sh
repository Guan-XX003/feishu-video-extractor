#!/bin/bash
set -euo pipefail

INSTALL_ROOT="${HOME}/Library/Application Support/FeishuVideoExtractor"
LABEL="com.growing.feishu-video-extractor"

printf '%s\n' '--- launchd ---'
launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | sed -n '1,45p' || true
printf '%s\n' '--- health ---'
curl --fail --silent --show-error http://127.0.0.1:8000/health || true
printf '\n%s\n' '--- recent errors ---'
tail -n 40 "$INSTALL_ROOT/logs/backend.stderr.log" 2>/dev/null || true


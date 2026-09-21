#!/bin/bash
set -euo pipefail

CLOUDFLARED_BIN="${HOME}/.local/bin/cloudflared"
CONFIG_PATH="${HOME}/.cloudflared/config.yml"
INSTALL_ROOT="${HOME}/Library/Application Support/FeishuVideoExtractor"
LOG_DIR="${INSTALL_ROOT}/logs"
PLIST_PATH="${HOME}/Library/LaunchAgents/com.growing.feishu-video-tunnel.plist"
LABEL="com.growing.feishu-video-tunnel"

if [ ! -x "$CLOUDFLARED_BIN" ]; then
  printf 'Missing cloudflared executable: %s\n' "$CLOUDFLARED_BIN" >&2
  exit 1
fi
if [ ! -f "$CONFIG_PATH" ]; then
  printf 'Missing tunnel config: %s\n' "$CONFIG_PATH" >&2
  exit 1
fi

"$CLOUDFLARED_BIN" tunnel --config "$CONFIG_PATH" ingress validate
mkdir -p "$LOG_DIR" "${HOME}/Library/LaunchAgents"

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$CLOUDFLARED_BIN</string>
    <string>tunnel</string>
    <string>--config</string>
    <string>$CONFIG_PATH</string>
    <string>--no-autoupdate</string>
    <string>run</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ProcessType</key>
  <string>Background</string>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/cloudflared.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/cloudflared.stderr.log</string>
</dict>
</plist>
EOF
chmod 600 "$PLIST_PATH"
plutil -lint "$PLIST_PATH" >/dev/null

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
launchctl enable "gui/$(id -u)/$LABEL"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

printf 'Installed and started: %s\n' "$LABEL"

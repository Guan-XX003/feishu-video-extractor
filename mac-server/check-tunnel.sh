#!/bin/bash
set -euo pipefail

TUNNEL_LABEL="com.growing.feishu-video-tunnel"
INSTALL_ROOT="${HOME}/Library/Application Support/FeishuVideoExtractor"
LAST_RESTART_FILE="${INSTALL_ROOT}/tunnel-watchdog-last-restart"
CONFIG_PATH="${HOME}/.cloudflared/config.yml"
LOCAL_HEALTH_URL="http://127.0.0.1:8000/health"
TUNNEL_READY_URL="http://127.0.0.1:20241/ready"

# Use the hostname of this dedicated tunnel, not a machine-specific URL.
hostname="$(awk '/^[[:space:]]*-[[:space:]]*hostname:[[:space:]]*/ {print $3; exit}' "$CONFIG_PATH")"
if [[ ! "$hostname" =~ ^[A-Za-z0-9.-]+$ ]]; then
  printf 'Cannot determine a valid tunnel hostname from %s\n' "$CONFIG_PATH" >&2
  exit 1
fi
PUBLIC_HEALTH_URL="https://${hostname}/health"

# A backend failure needs backend attention; restarting the tunnel will not fix it.
if ! curl --fail --silent --show-error --connect-timeout 2 --max-time 5 \
  "$LOCAL_HEALTH_URL" >/dev/null 2>&1; then
  exit 0
fi

if curl --fail --silent --show-error --connect-timeout 2 --max-time 5 \
    "$TUNNEL_READY_URL" >/dev/null 2>&1 && \
   curl --fail --silent --show-error --connect-timeout 5 --max-time 10 \
    "$PUBLIC_HEALTH_URL" >/dev/null 2>&1; then
  exit 0
fi

now="$(date +%s)"
last_restart=0
if [ -f "$LAST_RESTART_FILE" ]; then
  read -r last_restart < "$LAST_RESTART_FILE" || last_restart=0
fi
case "$last_restart" in
  ''|*[!0-9]*) last_restart=0 ;;
esac

# Avoid a restart loop during a wider network outage.
if [ $((now - last_restart)) -lt 300 ]; then
  exit 0
fi

printf '%s\n' "$now" > "$LAST_RESTART_FILE"
printf '%s Tunnel unhealthy; restarting %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$TUNNEL_LABEL"
launchctl kickstart -k "gui/$(id -u)/${TUNNEL_LABEL}"

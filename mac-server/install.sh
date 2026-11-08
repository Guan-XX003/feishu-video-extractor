#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_ROOT="${HOME}/Library/Application Support/FeishuVideoExtractor"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${LAUNCH_AGENTS_DIR}/com.growing.feishu-video-extractor.plist"
LABEL="com.growing.feishu-video-extractor"

PUBLIC_URL="http://127.0.0.1:8000"
ALLOWED_ORIGIN="https://your-company.feishu.cn"
EXPECTED_PACK_ID="replit_3272d3cf20efe80b,replit_324c5cc92959ef25"
BROWSER="edge"

usage() {
  printf '%s\n' "Usage: $0 [--public-url https://video.example.com] [--origin https://company.feishu.cn] [--pack-id ID] [--browser edge|chrome]"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --public-url) PUBLIC_URL="${2:?missing public URL}"; shift 2 ;;
    --origin) ALLOWED_ORIGIN="${2:?missing Feishu origin}"; shift 2 ;;
    --pack-id) EXPECTED_PACK_ID="${2:?missing shortcut ID}"; shift 2 ;;
    --browser) BROWSER="${2:?missing browser}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$BROWSER" in
  edge|chrome) ;;
  *) printf 'Browser must be edge or chrome.\n' >&2; exit 2 ;;
esac
case "$PUBLIC_URL" in
  http://127.0.0.1:8000|https://*) ;;
  *) printf 'Public URL must be local test URL or HTTPS.\n' >&2; exit 2 ;;
esac
case "$ALLOWED_ORIGIN" in
  https://your-company.feishu.cn)
    printf 'Set your Feishu origin with --origin https://YOUR_TENANT.feishu.cn before installing.\n' >&2
    exit 2 ;;
  https://*) ;;
  *) printf 'Feishu origin must use HTTPS.\n' >&2; exit 2 ;;
esac

PYTHON_BIN="$(command -v python3.12 || command -v python3 || true)"
if [ -z "$PYTHON_BIN" ]; then
  printf 'Python 3.12 was not found.\n' >&2
  exit 1
fi

mkdir -p "$INSTALL_ROOT/backend" "$INSTALL_ROOT/cache" "$INSTALL_ROOT/logs" \
  "$INSTALL_ROOT/browser-profile/Default" "$LAUNCH_AGENTS_DIR"
rm -rf "$INSTALL_ROOT/backend/app"
cp -R "$PROJECT_ROOT/backend/app" "$INSTALL_ROOT/backend/"
cp "$PROJECT_ROOT/backend/requirements.txt" "$INSTALL_ROOT/backend/requirements.txt"

if [ ! -x "$INSTALL_ROOT/.venv/bin/python" ]; then
  "$PYTHON_BIN" -m venv "$INSTALL_ROOT/.venv"
fi
"$INSTALL_ROOT/.venv/bin/python" -m pip install --upgrade pip
"$INSTALL_ROOT/.venv/bin/python" -m pip install -r "$INSTALL_ROOT/backend/requirements.txt"

ENV_PATH="$INSTALL_ROOT/backend.env"
if [ -f "$ENV_PATH" ]; then
  TICKET_SECRET="$({ sed -n 's/^TICKET_SECRET=//p' "$ENV_PATH" || true; } | head -n 1)"
else
  TICKET_SECRET=""
fi
if [ "${#TICKET_SECRET}" -lt 32 ]; then
  TICKET_SECRET="$("$PYTHON_BIN" -c 'import secrets; print(secrets.token_urlsafe(48))')"
fi

PROFILE_PATH="$INSTALL_ROOT/browser-profile/Default"
cat > "$ENV_PATH" <<EOF
ALLOWED_ORIGINS=$ALLOWED_ORIGIN
PUBLIC_BASE_URL=$PUBLIC_URL
MAX_VIDEO_SIZE_MB=30
MAX_AUDIO_SOURCE_SIZE_MB=500
DOWNLOAD_CONCURRENCY=2
TICKET_TTL_SECONDS=900
PREPARED_VIDEO_DIR="$INSTALL_ROOT/cache"
ALLOWED_VIDEO_DOMAINS=douyin.com,iesdouyin.com,tiktok.com,xiaohongshu.com,xhslink.com,bilibili.com,b23.tv,kuaishou.com
TICKET_SECRET=$TICKET_SECRET
REQUIRE_BASE_SIGNATURE=true
EXPECTED_PACK_ID=$EXPECTED_PACK_ID
COOKIES_FILE=
COOKIES_CONTENT=
COOKIES_FROM_BROWSER=$BROWSER
COOKIES_BROWSER_PROFILE="$PROFILE_PATH"
BROWSER_USER_AGENT=
BROWSER_DEBUG_URL=http://127.0.0.1:9222
BROWSER_WARMUP_SECONDS=3
WORKER_ENABLED=false
EOF
chmod 600 "$ENV_PATH"

cp "$SCRIPT_DIR/run-backend.sh" "$INSTALL_ROOT/run-backend.sh"
cp "$SCRIPT_DIR/open-douyin-login.command" "$INSTALL_ROOT/open-douyin-login.command"
chmod 700 "$INSTALL_ROOT/run-backend.sh" "$INSTALL_ROOT/open-douyin-login.command"

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string>
    <string>-s</string>
    <string>$INSTALL_ROOT/run-backend.sh</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ProcessType</key>
  <string>Background</string>
  <key>StandardOutPath</key>
  <string>$INSTALL_ROOT/logs/backend.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$INSTALL_ROOT/logs/backend.stderr.log</string>
</dict>
</plist>
EOF
chmod 600 "$PLIST_PATH"
plutil -lint "$PLIST_PATH" >/dev/null

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
launchctl enable "gui/$(id -u)/$LABEL"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

printf '%s\n' "Mac backend installed."
printf 'Runtime: %s\n' "$INSTALL_ROOT"
printf 'Health:  http://127.0.0.1:8000/health\n'
printf 'Login:   %s\n' "$INSTALL_ROOT/open-douyin-login.command"

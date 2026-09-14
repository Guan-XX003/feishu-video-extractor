#!/usr/bin/env bash
set -euo pipefail

browser_name="${1:-chrome}"
script_dir="$(cd "$(dirname "$0")" && pwd)"
yt_dlp_bin="$script_dir/.venv/bin/yt-dlp"
output_file="$script_dir/cookies.douyin.txt"
temp_cookie_dir="$(mktemp -d /tmp/feishu-douyin-cookies.XXXXXX)"
temp_cookie_file="$temp_cookie_dir/cookies.txt"

cleanup() {
  rm -f "$temp_cookie_file"
  rmdir "$temp_cookie_dir" 2>/dev/null || true
}
trap cleanup EXIT

if [[ ! -x "$yt_dlp_bin" ]]; then
  echo "未找到 $yt_dlp_bin，请先创建后端虚拟环境。" >&2
  exit 1
fi

"$yt_dlp_bin" \
  --cookies-from-browser "$browser_name" \
  --cookies "$temp_cookie_file" \
  --simulate \
  --no-playlist \
  "https://v.douyin.com/DNiHht4F72A/"

awk 'BEGIN { FS = OFS = "\t"; print "# Netscape HTTP Cookie File" }
  /^# Netscape HTTP Cookie File/ { next }
  /^#/ && !/^#HttpOnly_/ { next }
  {
    domain = $1
    sub(/^#HttpOnly_/, "", domain)
    if (domain ~ /(^|\.)douyin\.com$/ || domain ~ /(^|\.)iesdouyin\.com$/) print
  }' "$temp_cookie_file" > "$output_file"

cookie_count="$(awk 'BEGIN { FS = "\t"; count = 0 } !/^#/ && NF >= 7 { count++ } /^#HttpOnly_/ && NF >= 7 { count++ } END { print count }' "$output_file")"
if [[ "$cookie_count" -eq 0 ]]; then
  echo "没有找到抖音 Cookie。请先在 $browser_name 登录抖音后重试。" >&2
  exit 1
fi

chmod 600 "$output_file"
echo "已导出 $cookie_count 条抖音 Cookie 到：$output_file"

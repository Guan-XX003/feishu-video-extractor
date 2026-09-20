#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")" && pwd)"
release_dir="${1:-$project_dir/release}"
version="$(date +%Y%m%d-%H%M%S)"
package_name="feishu-video-extractor-agent-kit-$version"
stage_dir="$(mktemp -d /tmp/feishu-video-agent-kit.XXXXXX)"

cleanup() {
  rm -rf "$stage_dir"
}
trap cleanup EXIT

mkdir -p "$release_dir" "$stage_dir/$package_name"

rsync -a \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='field-shortcut/node_modules' \
  --exclude='backend/.venv' \
  --exclude='backend/cookies*.txt' \
  --exclude='.env' \
  --exclude='dist' \
  --exclude='field-shortcut/output' \
  --exclude='.pytest_cache' \
  --exclude='__pycache__' \
  --exclude='*.tsbuildinfo' \
  --exclude='release' \
  "$project_dir/" "$stage_dir/$package_name/"

if find "$stage_dir/$package_name" -type f \( -name '.env' -o -name 'cookies*.txt' \) | grep -q .; then
  echo "Refusing to package: secret-bearing files are present." >&2
  exit 1
fi

tar_path="$release_dir/$package_name.tar.gz"
zip_path="$release_dir/$package_name.zip"

tar -czf "$tar_path" -C "$stage_dir" "$package_name"
if command -v zip >/dev/null 2>&1; then
  (cd "$stage_dir" && zip -qr "$zip_path" "$package_name")
else
  echo "zip is unavailable; generated TAR.GZ only." >&2
fi

echo "Generated migration package(s):"
echo "  $tar_path"
[[ -f "$zip_path" ]] && echo "  $zip_path"

if command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "$tar_path" "$zip_path" 2>/dev/null || true
fi

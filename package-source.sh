#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")" && pwd)"
parent_dir="$(dirname "$project_dir")"
archive_path="${1:-$parent_dir/feishu-video-extractor-source.tar.gz}"

tar \
  --exclude='node_modules' \
  --exclude='backend/.venv' \
  --exclude='backend/cookies*.txt' \
  --exclude='*.env' \
  --exclude='field-shortcut/output' \
  --exclude='.pytest_cache' \
  --exclude='__pycache__' \
  -czf "$archive_path" \
  -C "$parent_dir" "$(basename "$project_dir")"

echo "已生成不含密钥的源码包：$archive_path"

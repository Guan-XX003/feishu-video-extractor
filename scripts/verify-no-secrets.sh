#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_dir"

failed=0
scan_output="$(mktemp /tmp/feishu-secret-scan.XXXXXX)"
trap 'rm -f "$scan_output"' EXIT

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  tracked="$(git ls-files)"
else
  tracked="$(find . -type f)"
fi

if printf '%s\n' "$tracked" | grep -E '(^|/)(cookies[^/]*\.txt|\.env)$' >/dev/null; then
  echo "ERROR: tracked cookie or .env file detected:"
  printf '%s\n' "$tracked" | grep -E '(^|/)(cookies[^/]*\.txt|\.env)$'
  failed=1
fi

patterns='(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|gho_[A-Za-z0-9]{20,}|sessionid[[:space:]]*[=:][[:space:]]*[A-Za-z0-9%_-]{16,}|refreshToken[[:space:]]*[=:]|accessToken[[:space:]]*[=:])'
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git grep -nEI "$patterns" -- ':!package-lock.json' ':!field-shortcut/package-lock.json' >"$scan_output" 2>/dev/null || true
else
  grep -RInE "$patterns" . \
    --exclude='package-lock.json' \
    --exclude-dir='node_modules' \
    --exclude-dir='.venv' \
    --exclude-dir='.git' >"$scan_output" 2>/dev/null || true
fi

if [[ -s "$scan_output" ]]; then
  echo "ERROR: possible secret material detected:"
  cat "$scan_output"
  failed=1
fi

if [[ "$failed" != "0" ]]; then
  exit 1
fi

echo "No tracked Cookie, .env, or obvious access-token material detected."

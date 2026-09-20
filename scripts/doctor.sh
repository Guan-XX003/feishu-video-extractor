#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")/.." && pwd)"
errors=0

check_command() {
  local name="$1"
  local required="$2"
  if command -v "$name" >/dev/null 2>&1; then
    printf 'OK   %-12s %s\n' "$name" "$(command -v "$name")"
  elif [[ "$required" == "required" ]]; then
    printf 'MISS %-12s required\n' "$name"
    errors=$((errors + 1))
  else
    printf 'INFO %-12s optional/not installed\n' "$name"
  fi
}

echo "Project: $project_dir"
check_command git required
check_command node required
check_command npm required
check_command gh optional
check_command railway optional
check_command docker optional

node_major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
python_bin=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && [[ "$("$candidate" -c 'import sys; print(int(sys.version_info >= (3, 10)))')" == "1" ]]; then
    python_bin="$candidate"
    break
  fi
done

if (( node_major < 20 )); then
  echo "MISS Node.js 20+ required; current: $(node --version 2>/dev/null || echo unavailable)"
  errors=$((errors + 1))
else
  echo "OK   Node.js version: $(node --version)"
fi

if [[ -z "$python_bin" ]]; then
  echo "MISS Python 3.10+ required"
  errors=$((errors + 1))
else
  echo "OK   Python: $(command -v "$python_bin") ($("$python_bin" --version 2>&1))"
fi

for file in backend/app/main.py field-shortcut/src/index.ts field-shortcut/src/config.ts backend/railway.env.example; do
  if [[ -f "$project_dir/$file" ]]; then
    echo "OK   file: $file"
  else
    echo "MISS file: $file"
    errors=$((errors + 1))
  fi
done

if (( errors > 0 )); then
  echo "Environment check failed with $errors issue(s)."
  exit 1
fi

echo "Environment check passed."

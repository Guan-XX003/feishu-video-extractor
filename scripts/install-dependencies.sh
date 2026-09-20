#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_dir"

python_bin=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && [[ "$("$candidate" -c 'import sys; print(int(sys.version_info >= (3, 10)))')" == "1" ]]; then
    python_bin="$candidate"
    break
  fi
done

if [[ -z "$python_bin" ]]; then
  echo "Python 3.10+ is required. Install it and retry." >&2
  exit 1
fi

npm ci
(cd field-shortcut && npm ci)

"$python_bin" -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/pip install -r backend/requirements.txt

echo "Dependencies installed. Run ./scripts/doctor.sh again, then execute tests."

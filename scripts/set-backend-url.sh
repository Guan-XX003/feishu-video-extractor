#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 https://your-backend.example.com" >&2
  exit 2
fi

backend_url="${1%/}"
if [[ ! "$backend_url" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?$ ]]; then
  echo "Production BACKEND_URL must be an HTTPS origin without a path." >&2
  exit 2
fi

project_dir="$(cd "$(dirname "$0")/.." && pwd)"
config_file="$project_dir/field-shortcut/src/config.ts"

python3 - "$config_file" "$backend_url" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
url = sys.argv[2]
text = path.read_text(encoding="utf-8")
updated, count = re.subn(
    r"export const BACKEND_URL = ['\"][^'\"]+['\"];",
    f"export const BACKEND_URL = '{url}';",
    text,
)
if count != 1:
    raise SystemExit("Could not update BACKEND_URL exactly once")
path.write_text(updated, encoding="utf-8")
PY

echo "Updated field-shortcut backend URL to: $backend_url"

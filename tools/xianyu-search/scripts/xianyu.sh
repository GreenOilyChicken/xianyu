#!/usr/bin/env sh
# POSIX convenience wrapper: uses the skill-local .venv when present.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -x "$ROOT/.venv/bin/python" ]; then
  exec "$ROOT/.venv/bin/python" "$ROOT/scripts/xianyu.py" "$@"
else
  exec python3 "$ROOT/scripts/xianyu.py" "$@"
fi

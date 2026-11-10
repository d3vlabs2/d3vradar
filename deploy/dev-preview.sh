#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -z "${RADAR_ENCRYPTION_KEY:-}" ]]; then
  if [[ ! -f .env ]]; then
    printf 'Run python3 deploy/configure.py --local first.\n' >&2
    exit 1
  fi
  set -a
  . ./.env
  set +a
fi
radar_python="${RADAR_PYTHON:-.venv/bin/python}"
radar_port="${PORT:-5173}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) radar_port="$2"; shift 2 ;;
    --host) shift 2 ;;
    --strictPort) shift ;;
    *) printf 'Unknown development option: %s\n' "$1" >&2; exit 1 ;;
  esac
done
exec "$radar_python" -m uvicorn radar.app:app --host 0.0.0.0 --port "$radar_port" --no-access-log

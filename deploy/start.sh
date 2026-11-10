#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 deploy/configure.py
if docker info >/dev/null 2>&1; then
  docker compose up -d --build
else
  sudo docker compose up -d --build
fi
printf '\nRadar is bound to 127.0.0.1:3740. Complete the Access and tunnel steps in README.md.\n'

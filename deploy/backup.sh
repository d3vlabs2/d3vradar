#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
backup_name="backups/radar-$(date +%Y%m%d-%H%M%S).sqlite"
# sqlite's backup API makes a consistent snapshot while Radar stays online.
docker compose exec -T radar python -c 'import sqlite3; src=sqlite3.connect("/data/radar.sqlite"); dest=sqlite3.connect("/tmp/radar-backup.sqlite"); src.backup(dest); dest.close(); src.close()'
docker compose cp radar:/tmp/radar-backup.sqlite "$backup_name"
printf 'Saved %s. Back up .env separately; its encryption key is required for restore.\n' "$backup_name"

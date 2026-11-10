#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
backup_name="backups/radar-all-workspaces-$(date +%Y%m%d-%H%M%S).tar.gz"
docker compose exec -T radar python -m radar.backup /data/.radar-backup.tar.gz
docker compose cp radar:/data/.radar-backup.tar.gz "$backup_name"
docker compose exec -T radar python -c 'from pathlib import Path; Path("/data/.radar-backup.tar.gz").unlink()'
printf 'Saved %s. Back up .env separately; its encryption key is required for restore.\n' "$backup_name"

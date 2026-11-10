#!/usr/bin/env bash
set -euo pipefail
main() {
  local source target branch
  source="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
  target="${1:-$HOME/jobradar}"
  if [[ ! -f "$target/compose.yaml" || ! -f "$target/.env" ]]; then
    echo 'Expected an existing Radar installation with compose.yaml and .env.' >&2; return 1
  fi
  if [[ -n "$(git -C "$source" status --porcelain)" ]]; then
    echo 'Source checkout has local changes. Commit or move them before updating.' >&2; return 1
  fi
  branch="$(git -C "$source" branch --show-current)"
  [[ "$branch" == main ]] || { echo 'Switch the source checkout to main first.' >&2; return 1; }
  git -C "$source" pull --ff-only origin main
  python3 "$source/deploy/check_ci.py" "$(git -C "$source" rev-parse HEAD)"
  # Snapshot all workspace DBs before replacing code; works with legacy images too.
  cd -- "$target"
  umask 077
  mkdir -p backups
  local backup_name="backups/radar-before-update-$(date +%Y%m%d-%H%M%S).tar.gz"
  sudo docker compose exec -T radar python - /tmp/radar-before-update.tar.gz < "$source/radar/backup.py"
  sudo docker compose cp radar:/tmp/radar-before-update.tar.gz "$backup_name"
  sudo chmod 600 "$backup_name"
  echo "Database backup saved: $backup_name"
  python3 "$source/deploy/apply_update.py" "$target"
  cd -- "$target"
  sudo docker compose up -d --build --force-recreate --wait --wait-timeout 120
  curl --fail --silent --show-error --retry 10 --retry-connrefused --retry-delay 2 http://127.0.0.1:3740/health
  echo
}
main "$@"

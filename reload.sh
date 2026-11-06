#!/usr/bin/env bash
# Restart the existing Odoo container. No build and no database restart.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
mkdir -p logs
log_file="logs/reload-$(date +%Y%m%d-%H%M%S)-$$.log"
exec > >(tee -a "$log_file") 2>&1
trap 'code=$?; printf "\n[ERROR] Reload failed (exit %s). Log: %s\n" "$code" "$log_file"; exit "$code"' ERR

printf '[RELOAD] %s\nLog: %s\n' "$(date -Iseconds)" "$log_file"
command -v docker >/dev/null || { printf 'Docker is not installed or is not on PATH.\n'; exit 1; }
docker compose version
docker info >/dev/null
docker compose config --quiet
container_id="$(docker compose ps -a -q odoo)"
if [[ -z "$container_id" ]]; then
    printf 'Odoo has no container yet. Run: bash setup.sh\n'
    exit 1
fi
if [[ -z "$(docker compose ps --status running -q db)" ]]; then
    printf 'PostgreSQL is not running. Start it with: docker compose up -d --wait db\n'
    exit 1
fi
docker compose restart odoo
docker compose ps
printf '\n[DONE] Odoo restarted. Check startup logs for application readiness.\n'
printf 'View Odoo logs: docker compose logs -f --tail=100 odoo\n'
printf 'Command log: %s\n' "$log_file"

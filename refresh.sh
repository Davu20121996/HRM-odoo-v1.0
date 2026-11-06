#!/usr/bin/env bash
# Rebuild the image and replace only the Odoo container, preserving volumes.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
mkdir -p logs
log_file="logs/refresh-$(date +%Y%m%d-%H%M%S)-$$.log"
exec > >(tee -a "$log_file") 2>&1
trap 'code=$?; printf "\n[ERROR] Refresh failed (exit %s). Log: %s\n" "$code" "$log_file"; exit "$code"' ERR

printf '[REFRESH] %s\nLog: %s\n' "$(date -Iseconds)" "$log_file"
command -v docker >/dev/null || { printf 'Docker is not installed or is not on PATH.\n'; exit 1; }
docker compose version
docker info >/dev/null
docker compose config --quiet
if [[ "${1:-}" == '--no-cache' && $# -eq 1 ]]; then
    docker compose build --no-cache odoo
elif [[ $# -eq 0 ]]; then
    docker compose build odoo
else
    printf 'Usage: bash refresh.sh [--no-cache]\n'
    exit 2
fi
# Build completes before replacing the current application container.
docker compose up -d --wait --wait-timeout 180 db
docker compose up -d --no-deps --no-build --force-recreate --wait --wait-timeout 180 odoo
docker compose ps
printf '\n[DONE] Odoo image rebuilt and container replaced. Data volumes preserved.\n'
printf 'View Odoo logs: docker compose logs -f --tail=100 odoo\n'
printf 'Command log: %s\n' "$log_file"

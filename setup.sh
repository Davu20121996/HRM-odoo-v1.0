#!/usr/bin/env bash
# First run: create local environment if missing, build, start PostgreSQL/Odoo.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
mkdir -p logs
log_file="logs/setup-$(date +%Y%m%d-%H%M%S)-$$.log"
exec > >(tee -a "$log_file") 2>&1
trap 'code=$?; printf "\n[ERROR] Setup failed (exit %s). Log: %s\n" "$code" "$log_file"; exit "$code"' ERR

printf '[SETUP] %s\nLog: %s\n' "$(date -Iseconds)" "$log_file"
command -v docker >/dev/null || { printf 'Docker is not installed or is not on PATH.\n'; exit 1; }
docker compose version
docker info >/dev/null
if [[ ! -f .env ]]; then
    cp -- .env.example .env
    printf 'Created .env from .env.example.\n'
fi
docker compose config --quiet
docker compose build odoo
docker compose up -d --wait --wait-timeout 180 db odoo
docker compose ps
printf '\n[DONE] Setup completed. Port: see docker compose ps above.\n'
printf 'View Odoo logs: docker compose logs -f --tail=100 odoo\n'
printf 'Command log: %s\n' "$log_file"

#!/usr/bin/env bash
set -euo pipefail

cd /home/kojima/work/kgrowth

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

INTERVAL="${KGROWTH_HERMES_COMMANDER_INTERVAL_SECONDS:-300}"

while true; do
  scripts/hermes_growth_commander_once.sh || true
  sleep "$INTERVAL"
done

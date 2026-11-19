#!/usr/bin/env bash
# Coleta de notícias do linky-dev (cron). Sem LLM, sem custo de API.
set -euo pipefail

REPO="${HOME}/linky-dev"
UV="${HOME}/.local/bin/uv"
LOG_DIR="${REPO}/data/logs"
mkdir -p "${LOG_DIR}"

cd "${REPO}"
exec /usr/bin/flock -n /tmp/linky-collect.lock \
  "${UV}" run --no-dev --frozen linky-collect --sources sources/sources.yaml --data data \
  >> "${LOG_DIR}/collect-$(date -u +%Y-%m).log" 2>&1

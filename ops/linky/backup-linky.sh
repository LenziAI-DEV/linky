#!/usr/bin/env bash
# Backup diário do volume do linky-agents (fila editorial, alertas, ledger, registros).
# Instalado em /opt/scripts/backup-linky.sh e chamado pelo cron às 03:15 (UTC).
# O snapshot é feito de dentro do container pela API de backup do SQLite (consistente
# mesmo com o serviço gravando). Retenção de 14 dias, como o backup do n8n.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/backups/linky}"
CONTAINER="${LINKY_CONTAINER:-linky-agents}"
TIMESTAMP="$(date +%F-%H%M%S)"
FILE="${BACKUP_DIR}/linky-data-${TIMESTAMP}.tar.gz"

umask 077
mkdir -p "$BACKUP_DIR" && chmod 700 "$BACKUP_DIR"
docker exec "$CONTAINER" python -m linky_agents.service.snapshot > "${FILE}.part"
gzip -t "${FILE}.part"                       # arquivo truncado não vira backup
mv "${FILE}.part" "$FILE"
echo "$(date -Is) backup criado: $FILE ($(du -h "$FILE" | cut -f1))"

find "$BACKUP_DIR" -type f -name "linky-data-*.tar.gz" -mtime +14 -delete
find "$BACKUP_DIR" -type f -name "*.part" -mtime +1 -delete

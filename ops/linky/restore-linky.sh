#!/usr/bin/env bash
# Restaura um backup do linky-agents.
#   restore-linky.sh <arquivo.tar.gz>              → substitui o volume linky_data (para o serviço)
#   restore-linky.sh <arquivo.tar.gz> <volume>     → restaura num volume à parte (teste)
# No modo padrão, o serviço é parado e o volume atual é copiado como está para
# $BACKUP_DIR/pre-restore-*.tar.gz antes de qualquer remoção. Sem essa cópia, nada é apagado.
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "uso: $0 <arquivo.tar.gz> [volume]" >&2
  exit 2
fi
ARCHIVE="$(realpath "$1")"
VOLUME="${2:-linky_data}"
BACKUP_DIR="${BACKUP_DIR:-/opt/backups/linky}"
COMPOSE="/opt/linky/compose.yaml"
IMAGE="python:3.12-slim"
[ -f "$ARCHIVE" ] || { echo "arquivo não encontrado: $ARCHIVE" >&2; exit 1; }
gzip -t "$ARCHIVE"

if [ "$VOLUME" = "linky_data" ]; then
  docker compose -f "$COMPOSE" stop linky-agents
  # serviço parado: a cópia crua do volume é consistente
  SAFETY="${BACKUP_DIR}/pre-restore-$(date +%F-%H%M%S).tar.gz"
  umask 077
  docker run --rm -v "${VOLUME}:/data:ro" "$IMAGE" tar czf - -C /data . > "$SAFETY"
  gzip -t "$SAFETY"
  echo "volume atual salvo em $SAFETY"
fi

docker run --rm -v "${VOLUME}:/data" -v "${ARCHIVE}:/backup.tar.gz:ro" "$IMAGE" sh -c \
  'find /data -mindepth 1 -delete && tar xzf /backup.tar.gz -C /data && chown -R 10001:10001 /data'

if [ "$VOLUME" = "linky_data" ]; then
  docker compose -f "$COMPOSE" start linky-agents
fi
echo "restaurado $ARCHIVE em $VOLUME"

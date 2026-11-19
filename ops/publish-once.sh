#!/usr/bin/env bash
# Dispara UMA vez um workflow de publicação já aprovado (T2, semana Mágico de Oz).
# Uso (crontab):  ops/publish-once.sh <workflow_id>
# - nunca roda duas vezes o mesmo workflow (marcador em data/published/<id>.done);
# - grava a saída completa em data/logs/publish-<id>.log, com o URN do post.
set -euo pipefail
id="${1:?informe o id do workflow}"
root="$HOME/linky-dev/data"
mkdir -p "$root/published" "$root/logs"
marker="$root/published/$id.done"
log="$root/logs/publish-$id.log"
exec 9>"$root/published/.lock"
flock -n 9 || { echo "$(date -Is) outra publicação em andamento" >>"$log"; exit 1; }
if [[ -e "$marker" ]]; then
  echo "$(date -Is) já publicado antes; nada a fazer" >>"$log"
  exit 0
fi
touch "$marker"  # antes de executar: em caso de falha, não reenvia sozinho (evita post duplicado)
echo "$(date -Is) executando $id" >>"$log"
docker exec -e N8N_RUNNERS_BROKER_PORT=5699 -e N8N_RUNNERS_ENABLED=false n8n \
  n8n execute --id="$id" --rawOutput >>"$log" 2>&1 \
  && echo "$(date -Is) ok" >>"$log" \
  || { echo "$(date -Is) FALHOU (marcador mantido; revisar antes de repetir)" >>"$log"; exit 1; }

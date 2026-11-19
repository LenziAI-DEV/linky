#!/usr/bin/env bash
# Liga ou desliga o modo sombra do linky-agents (ADR 0004) e recria só este container.
# Uso, como o usuário de deploy na VPS:
#   ~/linky-dev/ops/linky/shadow.sh off              # publicação real a partir de agora
#   ~/linky-dev/ops/linky/shadow.sh on               # volta ao modo sombra
#   ~/linky-dev/ops/linky/shadow.sh off 2026-11-20   # só age nesse dia (trava para cron de uso único)
# n8n, Traefik, Postgres e outro-servico ficam intactos.
set -euo pipefail

mode="${1:-}"
day="${2:-}"
case "$mode" in
  on|off) ;;
  *) echo "uso: shadow.sh on|off [AAAA-MM-DD]" >&2; exit 2 ;;
esac
if [ -n "$day" ] && [ "$(TZ=America/Sao_Paulo date +%F)" != "$day" ]; then
  exit 0
fi

ENV=/opt/linky/.env
if grep -q '^LINKY_SHADOW=' "$ENV"; then
  sed -i "s/^LINKY_SHADOW=.*/LINKY_SHADOW=$mode/" "$ENV"
else
  echo "LINKY_SHADOW=$mode" >> "$ENV"
fi
docker compose -f /opt/linky/compose.yaml up -d --force-recreate linky-agents

for _ in $(seq 1 30); do
  if [ "$(docker inspect -f '{{.State.Health.Status}}' linky-agents 2>/dev/null)" = "healthy" ]; then
    echo "$(date -u +%FT%TZ) $(docker logs linky-agents 2>&1 | grep 'modo sombra' | tail -1)"
    "$(dirname "$0")/check-egress.sh"   # healthy não basta: sem saída, nenhum agente roda
    exit 0
  fi
  sleep 2
done
echo "linky-agents não ficou healthy em 60 s; ver: docker logs linky-agents" >&2
exit 1

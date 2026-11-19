#!/usr/bin/env bash
# Atualiza e (re)sobe o linky-agents na VPS. Rodar como o usuário de deploy, de qualquer lugar:
#   ~/linky-dev/ops/linky/deploy.sh
# Só mexe no container linky-agents: n8n, Traefik, Postgres e outro-servico ficam intactos.
set -euo pipefail

REPO="$HOME/linky-dev"
DEST="/opt/linky"

cd "$REPO"
# O git pull troca este arquivo por um novo, mas o bash segue no antigo, que já estava aberto
# (deploy de 17/11: a checagem de saída nova não rodou). Depois do pull, roda a versão nova.
if [ -z "${LINKY_DEPLOY_PULLED:-}" ]; then
  git pull --ff-only
  LINKY_DEPLOY_PULLED=1 exec "$REPO/ops/linky/deploy.sh" "$@"
fi
SHA="$(git rev-parse --short HEAD)"

docker build -q -f ops/linky/Dockerfile -t "linky-agents:$SHA" -t linky-agents:latest .

if [ ! -f "$DEST/.env" ]; then
  echo "Falta $DEST/.env com LINKY_SERVICE_TOKEN (ver ops/README.md)" >&2
  exit 1
fi
install -m 644 ops/linky/compose.yaml "$DEST/compose.yaml"
docker compose -f "$DEST/compose.yaml" up -d

for _ in $(seq 1 30); do
  state="$(docker inspect -f '{{.State.Health.Status}}' linky-agents 2>/dev/null || true)"
  if [ "$state" = "healthy" ]; then
    echo "linky-agents:$SHA no ar (healthy)"
    "$REPO/ops/linky/check-egress.sh"   # healthy não basta: sem saída, nenhum agente roda
    # guarda as 3 imagens mais recentes deste serviço; as outras imagens da VPS não são tocadas
    docker image ls linky-agents --format '{{.Tag}}' | grep -vx latest | tail -n +4 \
      | xargs -r -I{} docker image rm "linky-agents:{}" >/dev/null || true
    exit 0
  fi
  sleep 2
done
echo "linky-agents não ficou healthy em 60 s; ver: docker logs linky-agents" >&2
exit 1

#!/usr/bin/env bash
# Confere, de dentro do container linky-agents, que ele resolve e alcança as APIs dos modelos
# (os base_url de config/models.yaml). Rodar como o usuário de deploy na VPS; o deploy.sh e o shadow.sh já
# chamam depois de recriar o container:
#   ~/linky-dev/ops/linky/check-egress.sh
# Sai com 1 (e diz qual host falhou) se não houver saída. Incidente de 17/11/2026: o container
# ficou só na rede interna do n8n e a curadoria das 07:00 falhou no DNS.
set -euo pipefail

CONTAINER="${LINKY_CONTAINER:-linky-agents}"

docker exec -i "$CONTAINER" python - <<'PY'
import socket
import sys
from urllib.parse import urlparse

import yaml

models = yaml.safe_load(open("/app/config/models.yaml", encoding="utf-8"))
hosts = sorted({urlparse(p["base_url"]).hostname for p in models["providers"].values()})
failed = []
for host in hosts:
    try:
        socket.create_connection((host, 443), timeout=5).close()
    except OSError as e:
        failed.append(f"{host}: {e}")
if failed:
    print("linky-agents SEM SAÍDA para a internet:", "; ".join(failed), file=sys.stderr)
    sys.exit(1)
print(f"saída ok ({', '.join(hosts)})")
PY

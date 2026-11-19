"""Adaptador HTTP da biblioteca padrão: traduz a conexão para `App.handle`.

Configuração por variáveis de ambiente (ver `ops/README.md`):
- `LINKY_SERVICE_TOKEN` (obrigatória): segredo compartilhado com o n8n, no cabeçalho
  `X-Linky-Token`;
- `LINKY_DATA_DIR` (padrão `data/` do repositório): onde ficam `editorial.db`, `alerts.db`,
  o ledger e os registros de execução;
- `LINKY_HOST` (padrão `0.0.0.0`) e `LINKY_PORT` (padrão `8080`);
- `LINKY_SHADOW` (padrão `on`): modo sombra (ADR 0004). Só `off`, `false` ou `0` fazem a
  publicação ir ao LinkedIn; qualquer valor desconhecido impede o serviço de subir;
- `LINKY_FORMS_URL` (padrão: o webhook `linky-form` em `n8n.example.com`): endereço dos
  formulários das decisões, usado nos links dos e-mails (ADR 0005).

Uso: python -m linky_agents.service
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..editorial import ROOT
from .app import DEFAULT_FORMS_URL, App

MAX_BODY = 1_000_000  # 1 MB: o maior corpo esperado é um lote de 5 pautas
log = logging.getLogger("linky.service")


class _Handler(BaseHTTPRequestHandler):
    app: App
    server_version = "linky-agents"
    sys_version = ""
    timeout = 30  # conexão parada não prende uma thread para sempre

    def _serve(self) -> None:
        raw_length = self.headers.get("Content-Length") or "0"
        length = int(raw_length) if raw_length.isdigit() else -1
        if length < 0:
            status, body = 400, {"error": "Content-Length inválido"}
        elif length > MAX_BODY:
            status, body = 413, {"error": "corpo grande demais"}
        else:
            raw = self.rfile.read(length) if length else b""
            try:
                status, body = self.app.handle(self.command, self.path, dict(self.headers), raw)
            except Exception:  # noqa: BLE001 - erro inesperado vira 500, e o serviço segue
                log.exception("erro inesperado em %s %s", self.command, self.path)
                status, body = 500, {"error": "erro interno"}
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = _serve

    def log_message(self, fmt: str, *args) -> None:  # sem cabeçalhos: o segredo não vaza
        if self.client_address[0] == "127.0.0.1" and self.path == "/health":
            return  # healthcheck do Docker, a cada minuto: só ruído
        log.info("%s %s", self.address_string(), fmt % args)


def shadow_from_env(raw: str | None) -> bool:
    value = (raw or "").strip().lower()
    if value in {"", "on", "true", "1"}:
        return True
    if value in {"off", "false", "0"}:
        return False
    raise ValueError(f"LINKY_SHADOW inválido: {raw!r} (use on ou off)")


def make_server(app: App, host: str, port: int) -> ThreadingHTTPServer:
    handler = type("Handler", (_Handler,), {"app": app})
    srv = ThreadingHTTPServer((host, port), handler)
    srv.daemon_threads = True
    return srv


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    token = os.environ.get("LINKY_SERVICE_TOKEN", "")
    if not token:
        print("LINKY_SERVICE_TOKEN não definido: o serviço não sobe sem segredo", file=sys.stderr)
        return 2
    try:
        shadow = shadow_from_env(os.environ.get("LINKY_SHADOW"))
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    data_dir = Path(os.environ.get("LINKY_DATA_DIR") or ROOT / "data")
    host = os.environ.get("LINKY_HOST", "0.0.0.0")
    port = int(os.environ.get("LINKY_PORT", "8080"))
    forms_url = os.environ.get("LINKY_FORMS_URL") or DEFAULT_FORMS_URL
    # Itens do coletor (cron no host), montados só leitura no container (compose.yaml)
    items = os.environ.get("LINKY_ITEMS_DIR")
    app = App(data_dir=data_dir, token=token, clock=lambda: datetime.now(UTC), shadow=shadow,
              forms_url=forms_url, items_dir=Path(items) if items else None)
    srv = make_server(app, host, port)

    def stop(*_):  # SIGTERM do Docker: termina o pedido em curso e sai
        threading.Thread(target=srv.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    log.info("linky-agents ouvindo em %s:%s, dados em %s, modo sombra: %s",
             host, port, data_dir, "ligado" if shadow else "DESLIGADO")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0

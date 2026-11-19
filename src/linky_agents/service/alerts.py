"""Caixa de alertas: o serviço grava aqui, e o n8n lê e confirma.

O harness não envia e-mail (D14). Cada alerta fica pendente até o n8n confirmar a leitura
(`ack`) depois de enviar o e-mail; ler sem confirmar não consome, então uma falha do envio
não perde o alerta.

Dois tipos de origem:
- custo: o gancho do ledger (`push`), com gasto e teto;
- operação (etapa E): publicação com falha ou travada e token do LinkedIn perto de vencer
  (`notify`), sem valores de custo. Uma chave de deduplicação garante que o mesmo aviso
  (por exemplo, "token vence em 7 dias") só entra uma vez, mesmo com o relógio de hora em hora.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from ..harness import Alert

_SCHEMA = """CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
    kind TEXT NOT NULL, scope TEXT NOT NULL, spent_usd REAL, cap_usd REAL,
    message TEXT NOT NULL, acked_at TEXT, dedupe_key TEXT UNIQUE, title TEXT)"""
_COLUMNS = "id, created_at, kind, scope, spent_usd, cap_usd, message, acked_at"


class AlertInbox:
    def __init__(self, db: Path, clock: Callable[[], datetime]):
        self.db = Path(db)
        self.clock = clock
        self._lock = threading.Lock()
        self._run(self._migrate)

    @staticmethod
    def _migrate(con: sqlite3.Connection) -> None:
        # Transação explícita: o sqlite3 do Python não abre transação sozinho para DDL, e
        # uma queda entre o RENAME e a cópia deixaria os alertas em alerts_v1.
        con.execute("BEGIN")
        cols = [r[1] for r in con.execute("PRAGMA table_info(alerts)")]
        if cols and "dedupe_key" not in cols:
            # Banco da etapa B/C: custo obrigatório e sem chave. Recria preservando os IDs
            # (o n8n confirma por ID) e o estado de leitura.
            con.execute("ALTER TABLE alerts RENAME TO alerts_v1")
            con.execute(_SCHEMA)
            con.execute(f"INSERT INTO alerts({_COLUMNS}) SELECT {_COLUMNS} FROM alerts_v1")
            con.execute("DROP TABLE alerts_v1")
        con.execute(_SCHEMA)
        con.execute(
            "CREATE TABLE IF NOT EXISTS linkedin_token "
            "(id INTEGER PRIMARY KEY CHECK (id = 1), expires_on TEXT NOT NULL, "
            "updated_at TEXT NOT NULL)"
        )

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db))
        con.row_factory = sqlite3.Row
        return con

    def _run(self, fn):
        with self._lock:
            con = self._connect()
            try:
                with con:
                    return fn(con)
            finally:
                con.close()

    def push(self, alert: Alert) -> None:
        """Gancho de alerta do harness (custo)."""
        self._run(lambda con: con.execute(
            "INSERT INTO alerts(created_at, kind, scope, spent_usd, cap_usd, message) "
            "VALUES(?,?,?,?,?,?)",
            (self.clock().isoformat(), alert.kind, alert.scope, alert.spent_usd,
             alert.cap_usd, alert.message),
        ))

    def notify(self, kind: str, scope: str, message: str, *, key: str | None = None,
               title: str | None = None) -> bool:
        """Alerta de operação. Com `key`, entra uma vez só (sem `key`, sempre entra);
        devolve se entrou. `title` (a pauta, por exemplo) vai no assunto do e-mail."""
        cur = self._run(lambda con: con.execute(
            "INSERT OR IGNORE INTO alerts(created_at, kind, scope, message, dedupe_key, title) "
            "VALUES(?,?,?,?,?,?)",
            (self.clock().isoformat(), kind, scope, message, key, title),
        ))
        return bool(cur.rowcount)

    def withdraw(self, key_prefix: str) -> int:
        """Retira os alertas ainda não enviados cuja chave começa com `key_prefix` (o problema
        se resolveu antes do e-mail). Ficam no banco, marcados como lidos: a chave continua
        valendo para a deduplicação. Devolve quantos retirou."""
        like = key_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        cur = self._run(lambda con: con.execute(
            "UPDATE alerts SET acked_at=? WHERE acked_at IS NULL AND dedupe_key LIKE ? "
            "ESCAPE '\\'",
            (self.clock().isoformat(), like),
        ))
        return cur.rowcount

    def pending(self) -> list[dict]:
        rows = self._run(lambda con: con.execute(
            "SELECT id, created_at, kind, scope, spent_usd, cap_usd, title, message FROM alerts "
            "WHERE acked_at IS NULL ORDER BY id"
        ).fetchall())
        return [dict(r) for r in rows]

    def ack(self, ids: list[int]) -> list[int]:
        """Confirma a leitura. Devolve só os IDs que estavam pendentes."""
        def op(con: sqlite3.Connection) -> list[int]:
            done = []
            for i in ids:
                cur = con.execute(
                    "UPDATE alerts SET acked_at=? WHERE id=? AND acked_at IS NULL",
                    (self.clock().isoformat(), i),
                )
                if cur.rowcount:
                    done.append(i)
            return done
        return self._run(op)

    # ---- validade do token do LinkedIn (registrada à mão quando a credencial é reconectada)
    def linkedin_token_expires_on(self) -> date | None:
        row = self._run(lambda con: con.execute(
            "SELECT expires_on FROM linkedin_token WHERE id = 1").fetchone())
        return date.fromisoformat(row[0]) if row else None

    def set_linkedin_token_expires_on(self, expires_on: date) -> None:
        self._run(lambda con: con.execute(
            "INSERT INTO linkedin_token(id, expires_on, updated_at) VALUES(1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET expires_on=excluded.expires_on, "
            "updated_at=excluded.updated_at",
            (expires_on.isoformat(), self.clock().isoformat()),
        ))

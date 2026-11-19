"""Registro de composições: a memória visual contra a repetição (ADR 0006).

Guarda a assinatura da composição de cada post (`compose.signature`: fundo + conjunto das
peças) em `compositions.db`, no volume de dados do serviço (`/data`, coberto pelo backup que
copia todo `*.db`). A mesma composição não se repete enquanto o post que a usou estiver entre
os últimos `window` posts registrados (5, em `tokens.json`).

Uso esperado na esteira: `check` antes de aceitar a imagem de um post; `record` quando a
imagem vira a do post (uma nova versão do mesmo post substitui a anterior e mantém a ordem);
`forget` quando o post é descartado.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from linky_agents.render.brand import load_brand
from linky_agents.render.compose import Composition, Violation, describe, signature

_SCHEMA = """
CREATE TABLE IF NOT EXISTS compositions (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    post TEXT NOT NULL UNIQUE,
    signature TEXT NOT NULL,
    description TEXT NOT NULL,
    pieces TEXT NOT NULL,
    recorded_at TEXT NOT NULL
)
"""


@dataclass(frozen=True)
class Record:
    post: str
    signature: str
    description: str
    recorded_at: str


class CompositionRegistry:
    def __init__(self, path: Path, window: int | None = None):
        self.path = Path(path)
        self.window = load_brand().rules["repetition_window"] if window is None else window
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute(_SCHEMA)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path)
        try:
            with db:  # transação: commit ou rollback
                yield db
        finally:
            db.close()

    def recent(self, excluding: str | None = None) -> list[Record]:
        """Os últimos `window` posts registrados (sem `excluding`), do mais antigo ao mais novo."""
        with self._db() as db:
            rows = db.execute(
                "SELECT post, signature, description, recorded_at FROM compositions "
                "WHERE post IS NOT ? ORDER BY seq DESC LIMIT ?",
                (excluding, self.window),
            ).fetchall()
        return [Record(*r) for r in reversed(rows)]

    def check(self, post: str, c: Composition) -> list[Violation]:
        """Violação de repetição, se a composição já foi usada nos últimos posts."""
        sig = signature(c)
        recent = self.recent(excluding=post)
        for age, rec in enumerate(reversed(recent), start=1):
            if rec.signature == sig:
                return [
                    Violation(
                        "repetição",
                        "composição",
                        f"mesma composição do post {rec.post!r}, de {age} posts atrás "
                        f"({describe(c)}). Ela só pode voltar depois de {self.window} posts: "
                        "troque ao menos uma peça ou o fundo.",
                    )
                ]
        return []

    def record(self, post: str, c: Composition) -> None:
        pieces = json.dumps([p.name for p in c.pieces], ensure_ascii=False)
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._db() as db:
            db.execute(
                "INSERT INTO compositions (post, signature, description, pieces, recorded_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(post) DO UPDATE SET "
                "signature = excluded.signature, description = excluded.description, "
                "pieces = excluded.pieces, recorded_at = excluded.recorded_at",
                (post, signature(c), describe(c), pieces, now),
            )

    def forget(self, post: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM compositions WHERE post = ?", (post,))

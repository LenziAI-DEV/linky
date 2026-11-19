"""Snapshot do volume do serviço para o backup diário: SQLite copiado pela API de backup
(consistente mesmo com o serviço gravando) e os demais arquivos como estão."""

import io
import sqlite3
import tarfile

from linky_agents.service.snapshot import snapshot


def test_snapshot_leva_bancos_consistentes_e_arquivos(tmp_path):
    data = tmp_path / "data"
    (data / "ledger").mkdir(parents=True)
    (data / "ledger" / "2026-11.jsonl").write_text('{"cost_usd": 0.01}\n', encoding="utf-8")
    con = sqlite3.connect(data / "editorial.db")
    con.execute("CREATE TABLE entries (id TEXT)")
    con.execute("INSERT INTO entries VALUES ('nubank')")
    con.commit()
    con.execute("INSERT INTO entries VALUES ('sem-commit')")  # transação aberta: fica de fora

    buf = io.BytesIO()
    snapshot(data, buf)
    con.close()

    out = tmp_path / "restaurado"
    with tarfile.open(fileobj=io.BytesIO(buf.getvalue()), mode="r:gz") as tar:
        names = sorted(tar.getnames())
        tar.extractall(out, filter="data")
    assert names == ["editorial.db", "ledger", "ledger/2026-11.jsonl"]
    rows = sqlite3.connect(out / "editorial.db").execute("SELECT id FROM entries").fetchall()
    assert rows == [("nubank",)]
    assert (out / "ledger" / "2026-11.jsonl").read_text(encoding="utf-8") == (
        '{"cost_usd": 0.01}\n'
    )


def test_snapshot_ignora_arquivos_auxiliares_do_sqlite(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    sqlite3.connect(data / "alerts.db").close()
    (data / "alerts.db-journal").write_bytes(b"lixo")
    (data / "alerts.db-wal").write_bytes(b"lixo")
    buf = io.BytesIO()
    snapshot(data, buf)
    with tarfile.open(fileobj=io.BytesIO(buf.getvalue()), mode="r:gz") as tar:
        assert tar.getnames() == ["alerts.db"]


def test_snapshot_escreve_em_fluxo_e_nao_deixa_copias_no_diretorio(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    sqlite3.connect(data / "editorial.db").close()

    class OnlyWrite:  # stdout de verdade: sem seek nem tell
        def __init__(self):
            self.chunks = []

        def write(self, b):
            self.chunks.append(bytes(b))
            return len(b)

    out = OnlyWrite()
    snapshot(data, out)
    with tarfile.open(fileobj=io.BytesIO(b"".join(out.chunks)), mode="r:gz") as tar:
        assert tar.getnames() == ["editorial.db"]
    assert sorted(p.name for p in data.iterdir()) == ["editorial.db"]

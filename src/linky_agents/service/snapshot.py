"""Snapshot do diretório de dados do serviço, em tar.gz, para o backup diário.

Bancos SQLite são copiados pela API de backup do SQLite: a cópia é consistente mesmo com o
serviço gravando (uma transação aberta fica de fora). Os outros arquivos (ledger, registros
de execução) vão como estão; são só acrescentados, então a cópia no máximo perde a última
linha em curso. Arquivos auxiliares do SQLite (-journal, -wal, -shm) ficam de fora.

O tar sai em fluxo (nada inteiro na memória) e as cópias dos bancos ficam num diretório
temporário dentro do próprio volume, apagado no fim: o container tem 256 MB e um /tmp
pequeno em memória.

Uso (de dentro do container): python -m linky_agents.service.snapshot > backup.tar.gz
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import BinaryIO

from ..editorial import ROOT

_SQLITE_AUX = ("-journal", "-wal", "-shm")
_TMP_PREFIX = ".snapshot-"


def snapshot(data_dir: Path, out: BinaryIO) -> None:
    data_dir = Path(data_dir)
    paths = sorted(
        p for p in data_dir.rglob("*")
        if not p.relative_to(data_dir).parts[0].startswith(_TMP_PREFIX)
    )
    with (
        tarfile.open(fileobj=out, mode="w|gz") as tar,
        tempfile.TemporaryDirectory(prefix=_TMP_PREFIX, dir=data_dir) as tmp,
    ):
        for path in paths:
            rel = path.relative_to(data_dir).as_posix()
            if path.name.endswith(_SQLITE_AUX):
                continue
            if path.is_dir():
                tar.add(path, arcname=rel, recursive=False)
            elif path.suffix == ".db":
                copy = Path(tmp) / rel.replace("/", "__")
                src, dst = sqlite3.connect(path), sqlite3.connect(copy)
                try:
                    src.backup(dst)
                finally:
                    src.close()
                    dst.close()
                tar.add(copy, arcname=rel)
            else:
                tar.add(path, arcname=rel)


def main() -> int:
    data_dir = Path(os.environ.get("LINKY_DATA_DIR") or ROOT / "data")
    snapshot(data_dir, sys.stdout.buffer)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())

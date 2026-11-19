"""Orquestração da esteira em produção (docs/ideas/producao-mvp.md).

O serviço chama três passos, cada um a partir de um workflow do n8n:
- `curate`: itens da coleta → triagem e curadoria → pautas na fila (antes do e-mail das 07:00);
- `draft`: pauta escolhida (ou com ajuste pedido) → redação, checagem e arte → post para aprovar;
- a imagem fica em `<data>/images/` e o n8n a lê por `GET /images/{nome}`.

Os agentes moram em `linky_agents.agents` (contratos em `agents/contracts.py`). `Agents` é a
fronteira: `RealAgents` importa os módulos só quando chamados, e os testes injetam um falso.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from ..agents.contracts import CardOut, Draft, ImageResult, compose_text
from ..editorial import Entry, Post
from ..harness import Harness

IMAGE_NAME = r"^[\w-][\w.-]*\.png$"
ART_REGISTRY = "compositions.db"  # o mesmo arquivo de `agents.art.REGISTRY_FILE`


def forget_dropped_art(data_dir: Path, entries: Iterable[Entry]) -> list[str]:
    """Tira do registro de composições da arte os posts descartados ou vencidos, para não
    pesarem na alternância de tema nem na regra de repetição. Devolve os IDs tirados."""
    from ..editorial import State
    from ..render.registry import CompositionRegistry

    path = Path(data_dir) / ART_REGISTRY
    dropped = {e.id for e in entries if e.state in (State.DISCARDED, State.EXPIRED)}
    if not dropped or not path.is_file():
        return []
    reg = CompositionRegistry(path)
    out: list[str] = []
    while gone := [r.post for r in reg.recent() if r.post in dropped and r.post not in out]:
        for post in gone:
            reg.forget(post)
        out += gone
    return out


class Agents(Protocol):
    def curate(self, items: list[dict], *, now: datetime, n_cards: int,
               exclude: list[str]) -> list[CardOut]: ...

    def write(self, entry: Entry, *, recent_hooks: list[str]) -> Draft: ...

    def image(self, entry: Entry, draft: Draft) -> ImageResult: ...


class RealAgents:
    """Os agentes de verdade, com o harness do serviço (um ledger e um teto só)."""

    def __init__(self, harness: Harness, data_dir: Path):
        self.harness, self.data_dir = harness, data_dir

    def curate(self, items, *, now, n_cards, exclude):
        from ..agents import pautas

        return pautas.curate(items, harness=self.harness, now=now, n_cards=n_cards,
                             exclude=exclude)

    def write(self, entry, *, recent_hooks):
        from ..agents import post

        sources = post.fetch_sources(entry.sources)
        return post.write(entry, sources, harness=self.harness, recent_hooks=recent_hooks)

    def image(self, entry, draft):
        from ..agents import art

        return art.make_image(entry, draft, harness=self.harness, data_dir=self.data_dir)


def load_items(items_dir: Path, start: datetime, end: datetime) -> list[dict]:
    """Itens do coletor publicados em [start, end]. Os arquivos são por dia de publicação em
    Brasília; lê do dia anterior ao início até o fim, para não perder a virada do dia."""
    out: list[dict] = []
    seen: set[str] = set()
    d = (start - timedelta(days=1)).date()
    while d <= end.date():
        f = items_dir / f"{d.isoformat()}.jsonl"
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                it = json.loads(line)
                pub = it.get("published_utc")
                if not pub or it.get("id") in seen:
                    continue
                if start <= datetime.fromisoformat(pub) <= end:
                    seen.add(it["id"])
                    out.append(it)
        d += timedelta(days=1)
    return out


def recent_exclusions(entries: Iterable[Entry], now: datetime, days: int = 14) -> list[str]:
    """IDs e títulos das pautas propostas nos últimos `days` dias: a curadoria não repete fato."""
    since = now - timedelta(days=days)
    out: list[str] = []
    for e in entries:
        if e.proposed_at >= since:
            out += [e.id, e.title]
    return out


def recent_hooks(entries: Iterable[Entry], n: int = 10) -> list[str]:
    """A primeira linha dos últimos posts prontos: o redator evita repetir o tipo de abertura."""
    done = sorted((e for e in entries if e.post is not None),
                  key=lambda e: e.slot or e.proposed_at, reverse=True)
    return [e.post.commentary.split("\n", 1)[0] for e in done[:n] if e.post]


def image_name(e: Entry) -> str:
    return f"{e.id}-v{len(e.adjustments) + 1}.png"


def post_from(draft: Draft, image: str, alt_text: str) -> Post:
    """O post para aprovar: a legenda padrão é o primeiro hook com a primeira leitura."""
    return Post(
        commentary=compose_text(draft.hooks[0].text, draft.body, draft.readings[0], draft.tail),
        alt_text=alt_text,
        image=image,
        hooks=[h.text for h in draft.hooks],
        readings=list(draft.readings),
        reading_is_felipe=draft.reading_is_felipe,
        body=draft.body,
        tail=draft.tail,
        notes=list(draft.notes),
    )


def recompose(post: Post, hook: int, reading: int | str) -> str:
    """A legenda com a escolha de Felipe. `reading` é o índice ou o texto que ele escreveu."""
    if not post.hooks:  # post feito à mão: não há o que recompor
        return post.commentary
    h = post.hooks[hook] if 0 <= hook < len(post.hooks) else post.hooks[0]
    if isinstance(reading, str):
        r = reading
    else:
        r = post.readings[reading] if 0 <= reading < len(post.readings) else post.readings[0]
    return compose_text(h, post.body, r, post.tail)

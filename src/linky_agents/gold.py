"""Gold set do T2 (semana Mágico de Oz): contrato do registro diário e ferramentas de apoio.

Cada dia do T2 vira um arquivo `eval/gold/AAAA-MM-DD.json`, versionado no repositório, porque
ele é o conjunto de referência das avaliações da Fase 1 (triagem, curadoria e redação):

- `triage`: rótulo de relevância para TODOS os itens do dia (avalia o agente de triagem);
- `scored`: notas da rubrica para os candidatos (avalia o ranking da curadoria);
- `cards`, `choice`: o que foi oferecido e o que Felipe escolheu, com o motivo;
- `post`: rascunho, versão final e edições (avalia o redator contra a voz real);
- `picks`: no lugar de `choice` e `post` nos lotes (domingo ou recuperação), até 5 cards e
  uma escolha por horário, cada uma com o próprio post. Pode apontar para uma pauta fora
  dos cards, quando Felipe pede outra.

Uso:
    linky-gold digest data/items/2026-11-06.jsonl     # lista compacta, agrupada por fato
    linky-gold digest data/items/2026-11-0[6-9].jsonl # vários dias (lote de domingo)
    linky-gold check eval/gold/2026-11-06.json        # valida e mostra o ranking calculado
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .stories import group_stories

RUBRIC_VERSION = "v0"
# Pesos da rubrica v0 (docs/editorial/rubrica.md). Recalibrar ao fim do T2 => nova versão.
WEIGHTS: dict[str, int] = {
    "relevance": 3,
    "novelty": 2,
    "evidence": 2,
    "brazil": 1,
    "positioning": 2,
    "conversation": 1,
}
# Desempate: evidência > relevância > novidade
TIEBREAK = ("evidence", "relevance", "novelty")

Score = Annotated[int, Field(ge=0, le=3)]
MAX_CARDS = 5  # 3 nos dias úteis; 5 no lote de domingo (PRD §7.6)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Scores(_Strict):
    relevance: Score
    novelty: Score
    evidence: Score
    brazil: Score
    positioning: Score
    conversation: Score

    @property
    def total(self) -> int:
        return sum(getattr(self, k) * w for k, w in WEIGHTS.items())

    def sort_key(self) -> tuple[int, ...]:
        return (self.total, *(getattr(self, k) for k in TIEBREAK))


class TriageLabel(_Strict):
    item_id: str
    relevant: bool
    reason: str | None = Field(default=None, description="Obrigatório quando relevant=false")

    @model_validator(mode="after")
    def _reason_when_discarded(self) -> TriageLabel:
        if not self.relevant and not self.reason:
            raise ValueError(f"{self.item_id}: item descartado precisa de motivo")
        return self


class ScoredItem(_Strict):
    item_id: str
    eliminated: str | None = Field(
        default=None, description="Filtro eliminatório que descartou o item (texto curto)"
    )
    scores: Scores | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _scores_or_elimination(self) -> ScoredItem:
        if (self.eliminated is None) == (self.scores is None):
            raise ValueError(f"{self.item_id}: informe scores OU eliminated, nunca os dois")
        return self


class Card(_Strict):
    rank: Annotated[int, Field(ge=1, le=MAX_CARDS)]
    item_ids: list[str] = Field(min_length=1, description="Item principal primeiro")
    title: Annotated[str, Field(min_length=3, max_length=120)]
    what_happened: str
    why_it_matters: str
    approach: str
    format: Literal["tese", "dado", "caso", "lancamento", "pesquisa"]
    sources: list[str] = Field(min_length=1)


class Choice(_Strict):
    card_rank: Annotated[int, Field(ge=1, le=MAX_CARDS)] | None = Field(
        default=None, description="None = nenhuma pauta hoje"
    )
    reason: str | None = None
    opinion: str | None = Field(default=None, description="A linha de opinião de Felipe")


class Post(_Strict):
    draft: str
    final: str | None = None
    edit_rounds: Annotated[int, Field(ge=0)] = 0
    edits: list[str] = Field(default_factory=list, description="O que Felipe mudou, em uma linha")
    image_spec: dict | None = None
    linkedin_urn: str | None = None
    published_at: str | None = None


class Pick(_Strict):
    """Uma escolha de um lote, ligada a um horário de publicação."""

    card_rank: Annotated[int, Field(ge=1, le=MAX_CARDS)] | None = Field(
        default=None, description="None = pauta fora dos cards (pedida por Felipe)"
    )
    item_ids: list[str] = Field(default_factory=list, description="Obrigatório fora dos cards")
    slot: datetime
    reason: str | None = None
    opinion: str | None = None
    post: Post | None = None

    @model_validator(mode="after")
    def _items_when_off_cards(self) -> Pick:
        if self.card_rank is None and not self.item_ids:
            raise ValueError("escolha fora dos cards precisa de item_ids")
        return self


class GoldDay(_Strict):
    date: date
    rubric_version: str = RUBRIC_VERSION
    items_file: str | list[str]
    items_count: Annotated[int, Field(ge=0)]
    triage: list[TriageLabel]
    scored: list[ScoredItem]
    cards: list[Card] = Field(max_length=MAX_CARDS)
    choice: Choice | None = None
    post: Post | None = None
    picks: list[Pick] = Field(default_factory=list)
    human_minutes: float | None = Field(default=None, description="Atenção de Felipe no dia")
    notes: list[str] = Field(default_factory=list, description="Observações para a calibração")

    @model_validator(mode="after")
    def _consistency(self) -> GoldDay:
        triaged = {t.item_id for t in self.triage}
        if len(triaged) != len(self.triage):
            raise ValueError("triage tem item_id repetido")
        if len(triaged) != self.items_count:
            raise ValueError(f"triage cobre {len(triaged)} itens, mas o dia tem {self.items_count}")
        relevant = {t.item_id for t in self.triage if t.relevant}
        for s in self.scored:
            if s.item_id not in relevant:
                raise ValueError(f"{s.item_id} recebeu nota mas não foi marcado como relevante")
        known = {s.item_id for s in self.scored}
        for c in self.cards:
            missing = [i for i in c.item_ids if i not in known]
            if missing:
                raise ValueError(f"card {c.rank} cita itens sem nota: {missing}")
        if [c.rank for c in self.cards] != list(range(1, len(self.cards) + 1)):
            raise ValueError("cards devem ter rank 1..n, em ordem")
        if self.choice and self.choice.card_rank and self.choice.card_rank > len(self.cards):
            raise ValueError("choice aponta para card inexistente")
        if self.picks and (self.choice or self.post):
            raise ValueError("use choice OU picks (com post em cada pick), nunca os dois")
        for p in self.picks:
            if p.card_rank and p.card_rank > len(self.cards):
                raise ValueError(f"pick aponta para card inexistente: {p.card_rank}")
            off = [i for i in p.item_ids if i not in relevant]
            if off:
                raise ValueError(f"pick cita item não relevante ou fora da triagem: {off}")
        if len({p.slot for p in self.picks}) != len(self.picks):
            raise ValueError("dois picks no mesmo horário")
        return self

    def ranking(self) -> list[ScoredItem]:
        """Itens não eliminados, da maior para a menor nota (com desempate da rubrica)."""
        ok = [s for s in self.scored if s.scores is not None]
        return sorted(ok, key=lambda s: s.scores.sort_key(), reverse=True)  # type: ignore[union-attr]


def load_items(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _digest(paths: list[Path], flat: bool = False) -> None:
    """Um número por fato: o item representante (com resumo) e as fontes irmãs abaixo, cada
    uma com o ID, porque a triagem do gold set rotula todos os itens. `flat`: sem agrupar."""
    items = [it for p in paths for it in load_items(p)]
    if flat:
        groups = [(it, ()) for it in items]
    else:
        groups = [(s.representative, s.siblings) for s in group_stories(items)]
        print(f"{len(items)} itens em {len(groups)} fatos")
    for n, (it, siblings) in enumerate(groups, 1):
        summary = it.get("summary", "")[:240]
        print(f"{n:02d} {it['id']} [{it['source']}] {it['title']}\n   {summary}\n   {it['url']}")
        for sib in siblings:
            print(f"   + {sib['id']} [{sib['source']}] {sib['title']}\n     {sib['url']}")


def _check(path: Path) -> int:
    day = GoldDay.model_validate_json(path.read_text(encoding="utf-8"))
    relevant = sum(t.relevant for t in day.triage)
    print(f"{day.date} · rubrica {day.rubric_version} · {day.items_count} itens · "
          f"{relevant} relevantes · {len(day.scored)} com nota")
    card_items = {i: c.rank for c in day.cards for i in c.item_ids}
    for pos, s in enumerate(day.ranking(), 1):
        mark = f"card {card_items[s.item_id]}" if s.item_id in card_items else ""
        print(f"  {pos:2d}. {s.scores.total:2d}/33  {s.item_id}  {mark}")  # type: ignore[union-attr]
    # top N por evento: itens do mesmo card contam uma vez só
    n, top_events = len(day.cards), []
    for s in day.ranking():
        event = card_items.get(s.item_id, s.item_id)
        if event not in top_events:
            top_events.append(event)
    off = [c.rank for c in day.cards if c.rank not in top_events[:n]]
    if off:
        print(f"  aviso: cards fora do top {n} da rubrica (por evento): {off}")
    for p in day.picks:
        what = f"card {p.card_rank}" if p.card_rank else f"fora dos cards {p.item_ids}"
        print(f"  escolha: {what} · horário {p.slot:%d/%m %H:%M} · motivo: {p.reason or '-'}")
    if day.choice:
        picked = day.choice.card_rank
        print(f"  escolha: {'card ' + str(picked) if picked else 'nenhuma'}"
              f" · motivo: {day.choice.reason or '-'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gold set do T2 (linky-dev)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    digest = sub.add_parser("digest", help="Lista compacta dos itens, agrupada por fato")
    digest.add_argument("items", nargs="+")
    digest.add_argument("--flat", action="store_true", help="um item por linha, sem agrupar")
    sub.add_parser("check", help="Valida um registro do gold set").add_argument("gold")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # console do Windows usa cp1252 por padrão
    if args.cmd == "digest":
        _digest([Path(p) for p in args.items], args.flat)
        return 0
    return _check(Path(args.gold))


if __name__ == "__main__":
    sys.exit(main())
